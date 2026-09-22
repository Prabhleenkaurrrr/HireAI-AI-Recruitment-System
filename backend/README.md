# HireAI Backend

FastAPI backend for the HireAI AI Recruitment System.

## Features
- Real signup/login with Argon2 password hashing
- JWT authentication and candidate/recruiter role protection
- SQLite database for prototype use (no Azure database cost)
- Resume extraction from PDF, DOCX, TXT and MD
- Job creation and applications
- Recruiter applicant review and shortlist/reject workflow
- One Foundry `gpt-4.1-mini` analysis per application, cached in SQLite
- AI output: match score, matching skills, missing skills, experience match, summary and interview questions

## Setup on Windows
```powershell
cd backend
py -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env` and add the Foundry project API key locally. Do not commit `.env`.

Run:
```powershell
uvicorn main:app --reload --port 8000
```
API docs: http://127.0.0.1:8000/docs

## AI cost control
The backend makes an AI call only when a recruiter clicks **Analyze with AI** for an application that has no saved analysis. Re-opening the analysis returns the saved database result and does not call Foundry again. Login, signup, resume upload, job creation, browsing jobs, applying and status changes do not call the model.

The backend does not send passwords to Foundry.
