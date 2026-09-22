import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import jwt
import fitz
from docx import Document
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from openai import OpenAI
from pwdlib import PasswordHash
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'hireai.db'}")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-change-this-secret")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 12

AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-mini").strip()

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Resume(Base):
    __tablename__ = "resumes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    resume_text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recruiter_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    skills: Mapped[str] = mapped_column(Text, nullable=False)
    experience: Mapped[str] = mapped_column(String(120), default="Not specified", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_candidate_job"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Applied", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class Analysis(Base):
    __tablename__ = "analyses"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    application_id: Mapped[int] = mapped_column(ForeignKey("applications.id"), unique=True, nullable=False)
    match_score: Mapped[int] = mapped_column(Integer, nullable=False)
    matching_skills: Mapped[str] = mapped_column(Text, nullable=False)
    missing_skills: Mapped[str] = mapped_column(Text, nullable=False)
    experience_match: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    interview_questions: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
Base.metadata.create_all(bind=engine)

app = FastAPI(title="HireAI API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:5501",
    "http://127.0.0.1:5501",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://hireai-recruitment.netlify.app",,
],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

password_hash = PasswordHash.recommended()
bearer = HTTPBearer(auto_error=False)


class SignupRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    confirm_password: str = Field(min_length=6, max_length=128)
    role: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    role: str


class JobCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    location: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=20)
    skills: str = Field(min_length=2)
    experience: str = Field(default="Not specified", max_length=120)


class StatusRequest(BaseModel):
    status: str

class ChatRequest(BaseModel):
    job_id: int
    message: str = Field(min_length=1, max_length=2000)

class RecruiterChatRequest(BaseModel):
    application_id: int
    message: str = Field(min_length=1, max_length=2000)

HIREAI_INSTRUCTIONS = """You are HireAI, an AI recruitment assistant.

Analyze a candidate resume against a specific job description. Use only job-relevant information from the resume and job description. Do not infer or use protected characteristics such as age, gender, religion, race, nationality, disability, marital status, or other protected traits. Do not make the final hiring decision; the recruiter makes that decision.

Return ONLY valid JSON with this exact structure:
{
  "match_score": 0,
  "matching_skills": [],
  "missing_skills": [],
  "experience_match": "",
  "summary": "",
  "interview_questions": []
}

Rules:
- match_score must be an integer from 0 to 100 and reflect only job-related evidence.
- matching_skills and missing_skills must be arrays of concise strings.
- experience_match must briefly compare relevant experience to the stated requirement.
- summary must be concise and evidence-based.
- interview_questions must contain 3 to 5 relevant questions based on the job and candidate.
- Never invent qualifications or experience not present in the input.
"""
INTERVIEW_CHAT_INSTRUCTIONS = """You are HireAI Interview Assistant.

You help a candidate prepare for an interview for a specific job.

Your responsibilities:
- Ask relevant interview questions.
- Explain interview concepts when the candidate asks.
- Give constructive feedback on answers.
- Help the candidate prepare based on the job description.
- Use the candidate's resume and job requirements when relevant.
- Focus only on job-related information.
- Never make hiring decisions.
- Never use protected characteristics such as age, gender, religion,
  race, nationality, disability, marital status, or other protected traits.
- Keep responses concise and practical.
- If conducting a mock interview, ask one question at a time.
"""

RECRUITER_ASSISTANT_INSTRUCTIONS = """You are HireAI Recruiter Interview Assistant.

You help a recruiter prepare job-relevant interview questions and evaluate what should be verified during an interview.

Use only information provided in:
- The job description
- The candidate resume
- The existing AI analysis

Focus only on job-related information.

Do not use or infer protected characteristics such as age, gender, religion,
race, nationality, disability, marital status, or other protected traits.

Do not make the final hiring decision.
The recruiter makes the final hiring decision.

You can:
- Suggest interview questions.
- Suggest follow-up questions.
- Explain what a recruiter should verify about a candidate's claimed skills.
- Identify areas of the resume that deserve clarification.
- Suggest technical or behavioral questions relevant to the job.

Do not invent candidate experience, qualifications, skills, or achievements.

Keep responses concise, practical and evidence-based.
"""


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "role": user.role, "name": user.name, "exp": now + timedelta(minutes=TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer), db: Session = Depends(get_db)) -> User:
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload.get("sub"))
    except (jwt.PyJWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(role: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role != role:
            raise HTTPException(status_code=403, detail=f"{role.title()} access required")
        return user
    return dependency


def parse_resume(filename: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        doc = fitz.open(stream=data, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
    elif suffix == ".docx":
        temp_path = BASE_DIR / "_temp_resume.docx"
        temp_path.write_bytes(data)
        try:
            doc = Document(str(temp_path))
            text = "\n".join(p.text for p in doc.paragraphs)
        finally:
            temp_path.unlink(missing_ok=True)
    elif suffix in {".txt", ".md"}:
        text = data.decode("utf-8", errors="ignore")
    else:
        raise HTTPException(status_code=400, detail="Only PDF, DOCX, TXT or MD resumes are supported")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 30:
        raise HTTPException(status_code=400, detail="Resume text is empty or too short to analyze")
    return text[:20000]


def get_analysis_dict(analysis: Analysis) -> dict:
    return {
        "id": analysis.id,
        "match_score": analysis.match_score,
        "matching_skills": json.loads(analysis.matching_skills),
        "missing_skills": json.loads(analysis.missing_skills),
        "experience_match": analysis.experience_match,
        "summary": analysis.summary,
        "interview_questions": json.loads(analysis.interview_questions),
        "created_at": analysis.created_at.isoformat(),
    }


def extract_json(text: str) -> dict:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise ValueError("Model did not return valid JSON")
        return json.loads(match.group(0))


def run_ai_analysis(resume_text: str, job: Job) -> dict:
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Foundry API key is not configured. Add it to backend/.env")

    client = OpenAI(base_url=AZURE_OPENAI_ENDPOINT, api_key=AZURE_OPENAI_API_KEY)
    user_input = f"""JOB TITLE: {job.title}
LOCATION: {job.location}
REQUIRED EXPERIENCE: {job.experience}
REQUIRED SKILLS: {job.skills}
JOB DESCRIPTION:
{job.description[:12000]}

CANDIDATE RESUME:
{resume_text[:20000]}

Analyze this candidate for this job and return only the requested JSON."""
    try:
        response = client.responses.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            instructions=HIREAI_INSTRUCTIONS,
            input=user_input,
            max_output_tokens=700,
        )
        raw = response.output_text
        result = extract_json(raw)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Foundry analysis failed: {str(exc)[:300]}")

    try:
        score = int(result.get("match_score"))
        if not 0 <= score <= 100:
            raise ValueError
        matching = result.get("matching_skills", [])
        missing = result.get("missing_skills", [])
        questions = result.get("interview_questions", [])
        if not isinstance(matching, list) or not isinstance(missing, list) or not isinstance(questions, list):
            raise ValueError
        return {
            "match_score": score,
            "matching_skills": [str(x) for x in matching[:15]],
            "missing_skills": [str(x) for x in missing[:15]],
            "experience_match": str(result.get("experience_match", "Not specified"))[:2000],
            "summary": str(result.get("summary", "No summary returned."))[:3000],
            "interview_questions": [str(x) for x in questions[:5]],
        }
    except Exception:
        raise HTTPException(status_code=502, detail="Foundry returned an invalid analysis format")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "HireAI API"}


@app.post("/api/auth/signup")
def signup(payload: SignupRequest, db: Session = Depends(get_db)):
    role = payload.role.lower().strip()
    if role not in {"candidate", "recruiter"}:
        raise HTTPException(status_code=400, detail="Role must be Candidate or Recruiter")
    if payload.password != payload.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    email = payload.email.lower().strip()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=payload.name.strip(), email=email, password_hash=password_hash.hash(payload.password), role=role)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"message": "Account created successfully", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}


@app.post("/api/auth/login")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    email = payload.email.lower().strip()
    role = payload.role.lower().strip()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not password_hash.verify(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if user.role != role:
        raise HTTPException(status_code=403, detail="Selected role does not match this account")
    return {"access_token": create_token(user), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}


@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}


@app.post("/api/candidate/resume")
def upload_resume(file: UploadFile = File(...), user: User = Depends(require_role("candidate")), db: Session = Depends(get_db)):
    data = file.file.read()
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Resume must be 5 MB or smaller")
    text = parse_resume(file.filename or "resume.txt", data)
    resume = db.scalar(select(Resume).where(Resume.candidate_id == user.id))
    if resume:
        resume.filename = file.filename or "resume"
        resume.resume_text = text
    else:
        resume = Resume(candidate_id=user.id, filename=file.filename or "resume", resume_text=text)
        db.add(resume)
    db.commit()
    return {"message": "Resume uploaded successfully", "filename": resume.filename, "characters": len(text)}


@app.get("/api/candidate/resume")
def resume_info(user: User = Depends(require_role("candidate")), db: Session = Depends(get_db)):
    resume = db.scalar(select(Resume).where(Resume.candidate_id == user.id))
    return {"has_resume": bool(resume), "filename": resume.filename if resume else None}


@app.get("/api/jobs")
def public_jobs(user: User = Depends(require_role("candidate")), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.is_active == True).order_by(Job.created_at.desc())).all()
    return [{"id": j.id, "title": j.title, "location": j.location, "description": j.description, "skills": j.skills, "experience": j.experience} for j in jobs]


@app.post("/api/jobs/{job_id}/apply")
def apply_job(job_id: int, user: User = Depends(require_role("candidate")), db: Session = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job or not job.is_active:
        raise HTTPException(status_code=404, detail="Job not found")
    if not db.scalar(select(Resume).where(Resume.candidate_id == user.id)):
        raise HTTPException(status_code=400, detail="Upload your resume before applying")
    existing = db.scalar(select(Application).where(Application.candidate_id == user.id, Application.job_id == job_id))
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied to this job")
    application = Application(candidate_id=user.id, job_id=job_id, status="Applied")
    db.add(application)
    db.commit()
    return {"message": "Application submitted", "application_id": application.id, "status": application.status}


@app.get("/api/candidate/applications")
def candidate_applications(user: User = Depends(require_role("candidate")), db: Session = Depends(get_db)):
    rows = db.execute(select(Application, Job, Analysis).join(Job, Application.job_id == Job.id).outerjoin(Analysis, Analysis.application_id == Application.id).where(Application.candidate_id == user.id).order_by(Application.created_at.desc())).all()
    return [{"application_id": a.id, "job_id": j.id, "title": j.title, "location": j.location, "status": a.status, "applied_at": a.created_at.isoformat(), "analysis": get_analysis_dict(an) if an else None} for a, j, an in rows]
@app.post("/api/candidate/interview-chat")
def interview_chat(
    payload: ChatRequest,
    user: User = Depends(require_role("candidate")),
    db: Session = Depends(get_db)
):
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Foundry API key is not configured"
        )

    # Candidate must have applied to this job
    application = db.scalar(
        select(Application).where(
            Application.candidate_id == user.id,
            Application.job_id == payload.job_id
        )
    )

    if not application:
        raise HTTPException(
            status_code=403,
            detail="You can use the interview assistant only for jobs you applied to"
        )

    job = db.get(Job, payload.job_id)

    if not job:
        raise HTTPException(
            status_code=404,
            detail="Job not found"
        )

    resume = db.scalar(
        select(Resume).where(Resume.candidate_id == user.id)
    )

    # Save candidate message
    user_message = ChatMessage(
        candidate_id=user.id,
        job_id=job.id,
        role="user",
        message=payload.message.strip()
    )

    db.add(user_message)
    db.commit()

    # Get previous conversation, limited to last 6 messages
    previous_messages = db.scalars(
        select(ChatMessage)
        .where(
            ChatMessage.candidate_id == user.id,
            ChatMessage.job_id == job.id
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(6)
    ).all()

    previous_messages.reverse()

    conversation = []

    for msg in previous_messages:
        conversation.append(
            f"{msg.role.upper()}: {msg.message}"
        )

    # Use existing analysis if available.
    # This avoids sending the full resume repeatedly and saves tokens.
    analysis = db.scalar(
        select(Analysis).where(
            Analysis.application_id == application.id
        )
    )

    analysis_context = ""

    if analysis:
        analysis_context = f"""
PREVIOUS AI ANALYSIS:
Match score: {analysis.match_score}
Matching skills: {analysis.matching_skills}
Missing skills: {analysis.missing_skills}
Experience match: {analysis.experience_match}
Summary: {analysis.summary}
Interview questions: {analysis.interview_questions}
"""

    resume_context = ""

    if resume:
        resume_context = resume.resume_text[:6000]

    user_input = f"""
JOB:
Title: {job.title}
Required experience: {job.experience}
Required skills: {job.skills}

JOB DESCRIPTION:
{job.description[:6000]}

CANDIDATE RESUME:
{resume_context}

{analysis_context}

RECENT CONVERSATION:
{chr(10).join(conversation)}

Answer the candidate's latest message.
"""

    try:
        client = OpenAI(
            base_url=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY
        )

        response = client.responses.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            instructions=INTERVIEW_CHAT_INSTRUCTIONS,
            input=user_input,
            max_output_tokens=500
        )

        answer = response.output_text.strip()

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Interview assistant failed: {str(exc)[:300]}"
        )

    # Save AI response
    assistant_message = ChatMessage(
        candidate_id=user.id,
        job_id=job.id,
        role="assistant",
        message=answer
    )

    db.add(assistant_message)
    db.commit()

    return {
        "job_id": job.id,
        "answer": answer
    }

@app.post("/api/recruiter/interview-assistant")
def recruiter_interview_assistant(
    payload: RecruiterChatRequest,
    user: User = Depends(require_role("recruiter")),
    db: Session = Depends(get_db)
):
    if not AZURE_OPENAI_ENDPOINT or not AZURE_OPENAI_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="Foundry API key is not configured"
        )

    row = db.execute(
        select(Application, Job, Resume, Analysis)
        .join(Job, Application.job_id == Job.id)
        .join(Resume, Resume.candidate_id == Application.candidate_id)
        .outerjoin(Analysis, Analysis.application_id == Application.id)
        .where(
            Application.id == payload.application_id,
            Job.recruiter_id == user.id
        )
    ).first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail="Application or resume not found"
        )

    application, job, resume, analysis = row

    analysis_context = "No AI analysis has been generated yet."

    if analysis:
        analysis_context = f"""
Match score: {analysis.match_score}
Matching skills: {analysis.matching_skills}
Missing skills: {analysis.missing_skills}
Experience match: {analysis.experience_match}
Summary: {analysis.summary}
Existing interview questions: {analysis.interview_questions}
"""

    user_input = f"""
JOB:
Title: {job.title}
Required experience: {job.experience}
Required skills: {job.skills}

JOB DESCRIPTION:
{job.description[:6000]}

CANDIDATE RESUME:
{resume.resume_text[:6000]}

EXISTING AI ANALYSIS:
{analysis_context}

RECRUITER'S QUESTION:
{payload.message.strip()}

Answer the recruiter's question using only the information above.
"""

    try:
        client = OpenAI(
            base_url=AZURE_OPENAI_ENDPOINT,
            api_key=AZURE_OPENAI_API_KEY
        )

        response = client.responses.create(
            model=AZURE_OPENAI_DEPLOYMENT,
            instructions=RECRUITER_ASSISTANT_INSTRUCTIONS,
            input=user_input,
            max_output_tokens=500
        )

        answer = response.output_text.strip()

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Recruiter assistant failed: {str(exc)[:300]}"
        )

    return {
        "application_id": application.id,
        "answer": answer
    }

@app.post("/api/recruiter/jobs")
def create_job(payload: JobCreate, user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    job = Job(recruiter_id=user.id, title=payload.title.strip(), location=payload.location.strip(), description=payload.description.strip(), skills=payload.skills.strip(), experience=payload.experience.strip())
    db.add(job)
    db.commit()
    db.refresh(job)
    return {"message": "Job created", "job": {"id": job.id, "title": job.title, "location": job.location, "description": job.description, "skills": job.skills, "experience": job.experience}}


@app.get("/api/recruiter/jobs")
def recruiter_jobs(user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    jobs = db.scalars(select(Job).where(Job.recruiter_id == user.id).order_by(Job.created_at.desc())).all()
    return [{"id": j.id, "title": j.title, "location": j.location, "description": j.description, "skills": j.skills, "experience": j.experience, "is_active": j.is_active} for j in jobs]


@app.get("/api/recruiter/jobs/{job_id}/applicants")
def applicants(job_id: int, user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    job = db.scalar(select(Job).where(Job.id == job_id, Job.recruiter_id == user.id))
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    rows = db.execute(select(Application, User, Analysis).join(User, Application.candidate_id == User.id).outerjoin(Analysis, Analysis.application_id == Application.id).where(Application.job_id == job_id).order_by(Application.created_at.desc())).all()
    return [{"application_id": a.id, "candidate_id": c.id, "candidate_name": c.name, "candidate_email": c.email, "status": a.status, "applied_at": a.created_at.isoformat(), "analysis": get_analysis_dict(an) if an else None} for a, c, an in rows]


@app.post("/api/recruiter/applications/{application_id}/analyze")
def analyze_application(application_id: int, user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    row = db.execute(select(Application, Job, Resume).join(Job, Application.job_id == Job.id).join(Resume, Resume.candidate_id == Application.candidate_id).where(Application.id == application_id, Job.recruiter_id == user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application or resume not found")
    application, job, resume = row
    existing = db.scalar(select(Analysis).where(Analysis.application_id == application_id))
    if existing:
        return {"cached": True, "analysis": get_analysis_dict(existing)}
    result = run_ai_analysis(resume.resume_text, job)
    analysis = Analysis(application_id=application_id, match_score=result["match_score"], matching_skills=json.dumps(result["matching_skills"]), missing_skills=json.dumps(result["missing_skills"]), experience_match=result["experience_match"], summary=result["summary"], interview_questions=json.dumps(result["interview_questions"]))
    db.add(analysis)
    db.commit()
    db.refresh(analysis)
    return {"cached": False, "analysis": get_analysis_dict(analysis)}


@app.post("/api/recruiter/applications/{application_id}/status")
def update_application_status(application_id: int, payload: StatusRequest, user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    allowed = {"Applied", "Under Review", "Shortlisted", "Rejected"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"Status must be one of: {', '.join(sorted(allowed))}")
    row = db.execute(select(Application, Job).join(Job, Application.job_id == Job.id).where(Application.id == application_id, Job.recruiter_id == user.id)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Application not found")
    application, _job = row
    application.status = payload.status
    db.commit()
    return {"message": "Application status updated", "status": application.status}


@app.get("/api/recruiter/shortlisted")
def shortlisted(user: User = Depends(require_role("recruiter")), db: Session = Depends(get_db)):
    rows = db.execute(select(Application, Job, User, Analysis).join(Job, Application.job_id == Job.id).join(User, Application.candidate_id == User.id).outerjoin(Analysis, Analysis.application_id == Application.id).where(Job.recruiter_id == user.id, Application.status == "Shortlisted").order_by(Application.created_at.desc())).all()
    return [{"application_id": a.id, "job_title": j.title, "candidate_name": c.name, "candidate_email": c.email, "status": a.status, "analysis": get_analysis_dict(an) if an else None} for a, j, c, an in rows]
