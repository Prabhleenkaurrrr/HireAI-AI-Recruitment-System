# HireAI — AI Recruitment System

A working AI-103 course project prototype using Microsoft Foundry `gpt-4.1-mini` for job-related resume analysis.

## Architecture

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python FastAPI
- **Database:** SQLite (local prototype, no extra Azure database service)
- **Authentication:** Argon2 password hashing + JWT
- **AI:** Microsoft Foundry project endpoint + `gpt-4.1-mini` Global Standard deployment
- **Resume parsing:** PyMuPDF for PDF, python-docx for DOCX

## Main workflow

### Candidate
1. Create account as Candidate.
2. Login.
3. Upload a resume.
4. Browse active jobs.
5. Apply to a job.
6. Track status: Applied / Under Review / Shortlisted / Rejected.

### Recruiter
1. Create account as Recruiter.
2. Login.
3. Create a job with description, skills and experience requirement.
4. View applicants.
5. Click **Analyze with AI** to run one real Foundry analysis.
6. Review matching skills, missing skills, experience match, summary and interview questions.
7. Shortlist/reject candidates.
8. The final hiring decision remains with the recruiter.

## AI cost-control design

Only the explicit **Analyze with AI** action calls Foundry. The analysis is stored in SQLite against the application. Re-opening an analyzed application returns the stored result, so repeated viewing does not create repeated AI calls.

No AI calls are made for authentication, job creation, resume upload, job browsing, applications or status changes.

## Security / responsible AI

- Passwords are hashed with Argon2.
- Passwords are never sent to Foundry.
- JWT protects backend routes.
- Candidate/recruiter roles are enforced server-side.
- API keys live in `.env`, which is ignored by Git.
- The AI prompt instructs the model to use only job-relevant evidence and avoid protected characteristics.
- AI is a recommendation/analysis tool; recruiter retains human oversight and the final decision.

## Run the project on Windows

### 1. Backend

Open PowerShell in the `backend` folder:

```powershell
py -m venv .venv
.venv\\Scripts\\activate
pip install -r requirements.txt
copy .env.example .env
```

Open `.env` and replace `PASTE_YOUR_FOUNDRY_PROJECT_API_KEY_HERE` with your Foundry project API key. Keep the key only on your machine.

Start API:

```powershell
uvicorn main:app --reload --port 8000
```

Leave this terminal running.

### 2. Frontend

Open a second PowerShell in the `frontend` folder:

```powershell
py -m http.server 5500
```

Open http://127.0.0.1:5500

Do not open `index.html` directly with `file://`; use the local server so browser requests work cleanly.

## Testing before demo

Backend automated tests are in `backend/tests/`.

```powershell
cd backend
.venv\\Scripts\\activate
pytest -q
```

Then manually test:

- Signup success
- Duplicate email rejected
- Wrong password rejected
- Wrong role rejected
- Candidate cannot call recruiter endpoints
- Resume upload with valid and invalid files
- Candidate cannot apply without a resume
- Duplicate application rejected
- Recruiter job validation
- Applicant list
- AI analysis with a real resume + JD
- Re-opening analysis does not create a second AI call
- Strong / partial / weak job matches
- Shortlist / reject / under-review status changes
- AI failure is shown to the user instead of displaying a fake score

## Foundry configuration

Use the endpoint/deployment shown in the Foundry **Call model** page. The project is designed for the Responses API and reads these values from `.env`:

```text
AZURE_OPENAI_ENDPOINT=https://hire.services.ai.azure.com/openai/v1
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_DEPLOYMENT=gpt-4.1-mini
```

If your Foundry Call model page shows a different endpoint, use that endpoint in `.env` instead of changing the source code.
