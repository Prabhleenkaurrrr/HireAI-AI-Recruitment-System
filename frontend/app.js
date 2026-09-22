const API_BASE = 'https://hireai-backend-akheftamfthch6d5.uaenorth-01.azurewebsites.net/api';
let selectedRole = 'candidate';
let currentUser = null;
let currentApplicants = [];

const $ = (id) => document.getElementById(id);

function toast(message, isError = false) {
  const el = $('toast'); el.textContent = message; el.style.background = isError ? '#b42318' : '#172033'; el.classList.add('show');
  setTimeout(() => el.classList.remove('show'), 3200);
}

function token() { return localStorage.getItem('hireai_token'); }
async function api(path, options = {}) {
  const headers = options.headers ? {...options.headers} : {};
  if (token()) headers.Authorization = `Bearer ${token()}`;
  if (!(options.body instanceof FormData) && options.body !== undefined) headers['Content-Type'] = 'application/json';
  const res = await fetch(`${API_BASE}${path}`, {...options, headers});
  const text = await res.text();
  let data = {}; try { data = text ? JSON.parse(text) : {}; } catch { data = {detail:text}; }
  if (!res.ok) throw new Error(data.detail || `Request failed (${res.status})`);
  return data;
}

function setRole(role) {
  selectedRole = role;
  document.querySelectorAll('.role-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.role === role));
}

document.querySelectorAll('.role-btn').forEach(btn => btn.addEventListener('click', () => setRole(btn.dataset.role)));
$('loginTab').onclick = () => { $('loginTab').classList.add('active'); $('signupTab').classList.remove('active'); $('loginForm').classList.remove('hidden'); $('signupForm').classList.add('hidden'); };
$('signupTab').onclick = () => { $('signupTab').classList.add('active'); $('loginTab').classList.remove('active'); $('signupForm').classList.remove('hidden'); $('loginForm').classList.add('hidden'); };

$('signupBtn').onclick = async () => {
  try {
    const name = $('signupName').value.trim(), email = $('signupEmail').value.trim(), password = $('signupPassword').value, confirm_password = $('signupConfirm').value;
    if (!name || !email || !password) return toast('Please fill all required fields.', true);
    await api('/auth/signup', {method:'POST', body: JSON.stringify({name,email,password,confirm_password,role:selectedRole})});
    toast('Account created. You can now log in.');
    $('loginEmail').value = email; $('signupPassword').value = ''; $('signupConfirm').value = '';
    $('loginTab').click();
  } catch (e) { toast(e.message, true); }
};

$('loginBtn').onclick = async () => {
  try {
    const email = $('loginEmail').value.trim(), password = $('loginPassword').value;
    if (!email || !password) return toast('Enter email and password.', true);
    const data = await api('/auth/login', {method:'POST', body: JSON.stringify({email,password,role:selectedRole})});
    localStorage.setItem('hireai_token', data.access_token); localStorage.setItem('hireai_user', JSON.stringify(data.user));
    currentUser = data.user; showApp();
  } catch (e) { toast(e.message, true); }
};

$('logoutBtn').onclick = () => { localStorage.removeItem('hireai_token'); localStorage.removeItem('hireai_user'); location.reload(); };

function showApp() {
  $('authView').classList.add('hidden'); $('appView').classList.remove('hidden');
  $('userGreeting').textContent = `Hi, ${currentUser.name}`; $('roleBadge').textContent = currentUser.role;
  if (currentUser.role === 'candidate') { $('candidateDashboard').classList.remove('hidden'); $('recruiterDashboard').classList.add('hidden'); loadCandidate(); }
  else { $('recruiterDashboard').classList.remove('hidden'); $('candidateDashboard').classList.add('hidden'); loadRecruiter(); }
}

async function loadCandidate() {
  try {
    const [resume, jobs, apps] = await Promise.all([api('/candidate/resume'), api('/jobs'), api('/candidate/applications')]);
    $('candidateResumeStat').textContent = resume.has_resume ? 'Uploaded' : 'Missing';
    $('candidateJobsStat').textContent = jobs.length; $('candidateAppsStat').textContent = apps.length;
    $('candidateShortlistedStat').textContent = apps.filter(a => a.status === 'Shortlisted').length;
    $('resumeInfo').textContent = resume.has_resume ? `Current file: ${resume.filename}` : 'No resume uploaded.';
    renderJobs(jobs); renderCandidateApplications(apps);
  } catch (e) { toast(e.message, true); }
}

function renderJobs(jobs) {
  const el = $('jobsList'); el.innerHTML = '';
  jobs.forEach(j => {
    const card = document.createElement('div'); card.className = 'job-card';
    card.innerHTML = `<h4>${escapeHtml(j.title)}</h4><div class="job-meta">${escapeHtml(j.location)} · ${escapeHtml(j.experience)}</div><div class="job-description">${escapeHtml(j.description)}</div><div class="chips">${j.skills.split(',').map(s=>`<span class="chip">${escapeHtml(s.trim())}</span>`).join('')}</div><div class="card-actions"><button class="primary apply-btn" data-id="${j.id}">Apply</button></div>`;
    el.appendChild(card);
  });
  el.querySelectorAll('.apply-btn').forEach(btn => btn.onclick = async () => { try { await api(`/jobs/${btn.dataset.id}/apply`, {method:'POST'}); toast('Application submitted.'); loadCandidate(); } catch(e){toast(e.message,true);} });
}

function renderCandidateApplications(apps) {
  const el = $('candidateApplications'); el.innerHTML = '';
  apps.forEach(a => {
    const statusClass = a.status === 'Shortlisted' ? 'shortlisted' : a.status === 'Rejected' ? 'rejected' : a.status === 'Under Review' ? 'review' : '';
    const div = document.createElement('div'); div.className = 'app-card'; div.innerHTML = `<h4>${escapeHtml(a.title)}</h4><div class="job-meta">${escapeHtml(a.location)}</div><span class="status ${statusClass}">${escapeHtml(a.status)}</span>${a.analysis ? `<div class="analysis-summary"><b>AI analysis available:</b> ${a.analysis.match_score}% match. ${escapeHtml(a.analysis.summary)}</div>` : ''}`;
    el.appendChild(div);
  });
}

$('uploadResumeBtn').onclick = async () => {
  const file = $('resumeFile').files[0]; if (!file) return toast('Choose a resume file first.', true);
  try { const fd = new FormData(); fd.append('file', file); await api('/candidate/resume',{method:'POST',body:fd}); toast('Resume uploaded successfully.'); loadCandidate(); } catch(e){toast(e.message,true);}
};



// ================= RECRUITER AI ASSISTANT =================

const recruiterAssistantModal = $('recruiterAssistantModal');
const recruiterAssistantCandidate = $('recruiterAssistantCandidate');

$('openRecruiterAssistant').onclick = () => {

  recruiterAssistantCandidate.innerHTML =
    '<option value="">Select a candidate</option>';

  currentApplicants.forEach(applicant => {
    const option = document.createElement('option');

    option.value = applicant.application_id;
    option.textContent =
      `${applicant.candidate_name} — ${applicant.candidate_email}`;

    recruiterAssistantCandidate.appendChild(option);
  });

  if (!currentApplicants.length) {
    return toast('No applicants available.', true);
  }

  recruiterAssistantCandidate.onchange = () => {
  const selectedId = Number(recruiterAssistantCandidate.value);
  const applicant = currentApplicants.find(
    a => a.application_id === selectedId
  );

  const content = $('recruiterAssistantContent');

  if (!applicant) {
    content.innerHTML = '<p class="muted">Select a candidate to view AI information.</p>';
    return;
  }

  if (!applicant.analysis) {
    content.innerHTML = `
      <p><strong>${escapeHtml(applicant.candidate_name)}</strong></p>
      <p class="muted">
        This candidate has not been analyzed by AI yet.
        Run <b>Analyze with AI</b> first.
      </p>
    `;
    return;
  }

  const a = applicant.analysis;

  content.innerHTML = `
    <div class="analysis-summary">
      <h4>${escapeHtml(applicant.candidate_name)}</h4>

      <p><strong>AI Match:</strong> ${a.match_score}%</p>

      <p><strong>Summary:</strong><br>
        ${escapeHtml(a.summary)}
      </p>

      <p><strong>Matching Skills:</strong></p>
      <div class="chips">
        ${a.matching_skills.map(skill =>
          `<span class="chip good">✓ ${escapeHtml(skill)}</span>`
        ).join('')}
      </div>

      <p><strong>Missing Skills:</strong></p>
      <div class="chips">
        ${a.missing_skills.map(skill =>
          `<span class="chip missing">${escapeHtml(skill)}</span>`
        ).join('')}
      </div>

      <p><strong>Experience Match:</strong><br>
        ${escapeHtml(a.experience_match)}
      </p>

      <h4>Existing Interview Questions</h4>

      ${a.interview_questions.map((q, i) =>
        `<div class="question">${i + 1}. ${escapeHtml(q)}</div>`
      ).join('')}
    </div>
  `;
};

  recruiterAssistantModal.classList.remove('hidden');
};

$('closeRecruiterAssistant').onclick = () => {
  recruiterAssistantModal.classList.add('hidden');
};

const recruiterAssistantInput = $('recruiterAssistantInput');
const sendRecruiterAssistant = $('sendRecruiterAssistant');
const recruiterAssistantMessages = $('recruiterAssistantMessages');

function addRecruiterAssistantMessage(message, role) {
  const div = document.createElement('div');
  div.className = `chat-message ${role}`;
  div.textContent = message;
  recruiterAssistantMessages.appendChild(div);
  recruiterAssistantMessages.scrollTop = recruiterAssistantMessages.scrollHeight;
}

async function askRecruiterAssistant() {
  const applicationId = recruiterAssistantCandidate.value;
  const message = recruiterAssistantInput.value.trim();

  if (!applicationId) {
    return toast('Please select a candidate first.', true);
  }

  if (!message) {
    return toast('Please enter a question.', true);
  }

  addRecruiterAssistantMessage(message, 'user');

  recruiterAssistantInput.value = '';
  sendRecruiterAssistant.disabled = true;
  sendRecruiterAssistant.textContent = 'Thinking...';

  try {
    const data = await api('/recruiter/interview-assistant', {
      method: 'POST',
      body: JSON.stringify({
        application_id: Number(applicationId),
        message: message
      })
    });

    addRecruiterAssistantMessage(data.answer, 'assistant');

  } catch (e) {
    addRecruiterAssistantMessage(
      'Sorry, I could not process your question. Please try again.',
      'assistant'
    );

    toast(e.message, true);

  } finally {
    sendRecruiterAssistant.disabled = false;
    sendRecruiterAssistant.textContent = 'Ask AI';
  }
}

sendRecruiterAssistant.onclick = askRecruiterAssistant;

recruiterAssistantInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    askRecruiterAssistant();
  }
});

recruiterAssistantModal.onclick = (e) => {
  if (e.target.id === 'recruiterAssistantModal') {
    recruiterAssistantModal.classList.add('hidden');
  }
};



// ================= AI INTERVIEW CHAT =================

const interviewChatModal = $('interviewChatModal');
const chatJobSelect = $('chatJobSelect');
const chatMessages = $('chatMessages');
const chatInput = $('chatInput');
const sendChatBtn = $('sendChatBtn');

$('openInterviewChat').onclick = async () => {
  try {
    const apps = await api('/candidate/applications');

    chatJobSelect.innerHTML = '<option value="">Select a job</option>';

    apps.forEach(app => {
      const option = document.createElement('option');
      option.value = app.job_id;
      option.textContent = app.title;
      chatJobSelect.appendChild(option);
    });

    if (!apps.length) {
      toast('Apply to a job first to use the interview assistant.', true);
      return;
    }

    chatMessages.innerHTML = `
      <div class="chat-message assistant">
        Hi! I'm your HireAI Interview Assistant.
        Select a job and ask me anything about your interview preparation.
      </div>
    `;

    interviewChatModal.classList.remove('hidden');
  } catch (e) {
    toast(e.message, true);
  }
};


$('closeInterviewChat').onclick = () => {
  interviewChatModal.classList.add('hidden');
};


interviewChatModal.onclick = (e) => {
  if (e.target.id === 'interviewChatModal') {
    interviewChatModal.classList.add('hidden');
  }
};


function addChatMessage(message, role) {
  const div = document.createElement('div');
  div.className = `chat-message ${role}`;
  div.textContent = message;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}


async function sendInterviewMessage() {
  const jobId = chatJobSelect.value;
  const message = chatInput.value.trim();

  if (!jobId) {
    return toast('Please select a job first.', true);
  }

  if (!message) {
    return toast('Please enter a message.', true);
  }

  addChatMessage(message, 'user');
  chatInput.value = '';

  sendChatBtn.disabled = true;
  sendChatBtn.textContent = 'Thinking...';

  try {
    const data = await api('/candidate/interview-chat', {
      method: 'POST',
      body: JSON.stringify({
        job_id: Number(jobId),
        message: message
      })
    });

    addChatMessage(data.answer, 'assistant');

  } catch (e) {
    addChatMessage(
      'Sorry, I could not process your message. Please try again.',
      'assistant'
    );
    toast(e.message, true);

  } finally {
    sendChatBtn.disabled = false;
    sendChatBtn.textContent = 'Send';
  }
}


sendChatBtn.onclick = sendInterviewMessage;


chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    sendInterviewMessage();
  }
});

async function loadRecruiter() {
  try {
    const [jobs, shortlisted] = await Promise.all([api('/recruiter/jobs'), api('/recruiter/shortlisted')]);
    renderRecruiterJobs(jobs); renderShortlisted(shortlisted);
    let total=0, scores=0, count=0; for (const j of jobs) { const a=await api(`/recruiter/jobs/${j.id}/applicants`); total += a.length; a.forEach(x=>{if(x.analysis){scores+=x.analysis.match_score;count++;}}); }
    $('recruiterJobsStat').textContent = jobs.filter(j=>j.is_active).length; $('recruiterApplicantsStat').textContent = total; $('recruiterShortlistedStat').textContent = shortlisted.length; $('recruiterAvgStat').textContent = count ? `${Math.round(scores/count)}%` : '—';
  } catch(e){toast(e.message,true);}
}

function renderRecruiterJobs(jobs) {
  const el=$('recruiterJobs'); el.innerHTML=''; jobs.forEach(j=>{const d=document.createElement('div');d.className='job-card';d.innerHTML=`<h4>${escapeHtml(j.title)}</h4><div class="job-meta">${escapeHtml(j.location)} · ${escapeHtml(j.experience)}</div><div class="job-description">${escapeHtml(j.description.slice(0,180))}${j.description.length>180?'…':''}</div><div class="card-actions"><button class="secondary view-apps" data-id="${j.id}" data-title="${escapeHtml(j.title)}">View applicants</button></div>`;el.appendChild(d);});
  el.querySelectorAll('.view-apps').forEach(b=>b.onclick=()=>loadApplicants(Number(b.dataset.id),b.dataset.title));
}

async function loadApplicants(jobId,title) {
  try { const data=await api(`/recruiter/jobs/${jobId}/applicants`); currentApplicants=data; $('applicantsPanel').classList.remove('hidden'); $('bulkActions').classList.remove('hidden'); $('applicantsTitle').textContent=`Applicants — ${title}`; renderApplicants(data); $('applicantsPanel').scrollIntoView({behavior:'smooth'}); } catch(e){toast(e.message,true);}
}

function renderApplicants(data) {
  const el = $('applicantsList');
  el.innerHTML = '';

  data.forEach(a => {
    const analysis = a.analysis;

    const d = document.createElement('div');
    d.className = 'app-card';

    d.innerHTML = `
      <div class="applicant-grid">

        <div>
        <div style="display:flex !important; flex-direction:row !important; align-items:center !important; justify-content:flex-start !important; gap:10px !important; margin-bottom:8px !important;">
  <input
    type="checkbox"
    class="applicant-checkbox"
    data-id="${a.application_id}"

    style="margin:0 !important; width:auto !important;"
  />
  <span style="font-size:14px !important;">Select</span>
</div>
  

  <h4>${escapeHtml(a.candidate_name)}</h4>

          <div class="job-meta">
            ${escapeHtml(a.candidate_email)}
            · Applied ${new Date(a.applied_at).toLocaleDateString()}
          </div>

          <span class="status ${
  a.status === 'Shortlisted'
    ? 'shortlisted'
    : a.status === 'Rejected'
    ? 'rejected'
    : ''
}">
  ${escapeHtml(a.status)}
</span>
        </div>

        <div class="score ${analysis ? '' : 'empty'}">
          ${analysis ? analysis.match_score + '%' : 'Not analyzed'}
        </div>

      </div>

      ${
        analysis
          ? `
            <div class="analysis-summary">
              ${escapeHtml(analysis.summary)}

              <div class="chips">
                ${analysis.matching_skills.map(x =>
                  `<span class="chip good">✓ ${escapeHtml(x)}</span>`
                ).join('')}

                ${analysis.missing_skills.map(x =>
                  `<span class="chip missing">Missing: ${escapeHtml(x)}</span>`
                ).join('')}
              </div>
            </div>
          `
          : ''
      }

      <div class="card-actions">

        <button
          class="secondary analyze-btn"
          data-id="${a.application_id}">
          ${analysis ? 'View AI analysis' : 'Analyze with AI'}
        </button>

        ${
          a.status !== 'Shortlisted'
            ? `<button
                class="primary status-btn"
                data-status="Shortlisted"
                data-id="${a.application_id}">
                Shortlist
              </button>`
            : ''
        }

        ${
          a.status !== 'Rejected'
            ? `<button
                class="ghost status-btn"
                data-status="Rejected"
                data-id="${a.application_id}">
                Reject
              </button>`
            : ''
        }



      </div>
    `;

    el.appendChild(d);
  });

  el.querySelectorAll('.analyze-btn').forEach(
    b => b.onclick = () => analyze(Number(b.dataset.id))
  );

  el.querySelectorAll('.status-btn').forEach(
    b => b.onclick = () =>
      changeStatus(Number(b.dataset.id), b.dataset.status)
  );
}

async function analyze(id){
  try { toast('Running one AI analysis…'); const data=await api(`/recruiter/applications/${id}/analyze`,{method:'POST'}); showAnalysis(data.analysis, data.cached); const item=currentApplicants.find(x=>x.application_id===id); if(item)item.analysis=data.analysis; renderApplicants(currentApplicants); loadRecruiterStatsOnly(); } catch(e){toast(e.message,true);}
}
// ================= BULK APPLICATION ANALYSIS =================

$('analyzeAllBtn').onclick = async () => {
  if (!currentApplicants.length) {
    return toast('No applicants available.', true);
  }

  const unanalyzed = currentApplicants.filter(a => !a.analysis);

  if (!unanalyzed.length) {
    return toast('All applicants are already analyzed.');
  }

  const btn = $('analyzeAllBtn');
  btn.disabled = true;

  try {
    for (let i = 0; i < unanalyzed.length; i++) {
      const applicant = unanalyzed[i];

      btn.textContent =
        `🤖 Analyzing ${i + 1}/${unanalyzed.length}...`;

      $('bulkStatus').textContent =
        `Analyzing ${applicant.candidate_name}...`;

      const data = await api(
        `/recruiter/applications/${applicant.application_id}/analyze`,
        { method: 'POST' }
      );

      applicant.analysis = data.analysis;

      renderApplicants(currentApplicants);
    }

    $('bulkStatus').textContent =
      `Analysis complete: ${unanalyzed.length} new applicant(s) analyzed.`;

    toast('All new applications analyzed successfully.');

    loadRecruiterStatsOnly();

  } catch (e) {
    toast(e.message, true);

    $('bulkStatus').textContent =
      'Analysis stopped because an error occurred.';
  } finally {
    btn.disabled = false;
    btn.textContent = '🤖 Analyze All Applications';
  }
};

// ================= SELECT TOP MATCHES =================

$('selectTopBtn').onclick = () => {
  const analyzedApplicants = currentApplicants
    .filter(a =>
      a.analysis &&
      a.status !== 'Shortlisted' &&
      a.status !== 'Rejected'
    )
    .sort((a, b) =>
      b.analysis.match_score - a.analysis.match_score
    );

  if (!analyzedApplicants.length) {
    return toast('No analyzed applicants available.', true);
  }

  const topMatches = analyzedApplicants.slice(0, 5);

  document.querySelectorAll('.applicant-checkbox').forEach(cb => {
    cb.checked = topMatches.some(
      a => a.application_id === Number(cb.dataset.id)
    );
  });

  $('bulkStatus').textContent =
    `${topMatches.length} top match(es) selected. Please review before shortlisting.`;

  toast(`${topMatches.length} top matches selected.`);
};

// ================= BULK STATUS ACTIONS =================

$('shortlistSelectedBtn').onclick = async () => {
  const selectedIds = Array.from(
    document.querySelectorAll('.applicant-checkbox:checked')
  ).map(cb => Number(cb.dataset.id));

  if (!selectedIds.length) {
    return toast('Please select at least one applicant.', true);
  }

  if (!confirm(`Shortlist ${selectedIds.length} selected applicant(s)?`)) {
    return;
  }

  try {
    for (const id of selectedIds) {
      await api(`/recruiter/applications/${id}/status`, {
        method: 'POST',
        body: JSON.stringify({
          status: 'Shortlisted'
        })
      });
    }

    toast(`${selectedIds.length} applicant(s) shortlisted successfully.`);
await loadRecruiter();

const selectedJob = document.querySelector('.view-apps[data-id]');
if (selectedJob) {
  await loadApplicants(
    Number(selectedJob.dataset.id),
    selectedJob.dataset.title
  );
}

  } catch (e) {
    toast(e.message, true);
  }
};

$('rejectSelectedBtn').onclick = async () => {
  const selectedIds = Array.from(
    document.querySelectorAll('.applicant-checkbox:checked')
  ).map(cb => Number(cb.dataset.id));

  if (!selectedIds.length) {
    return toast('Please select at least one applicant.', true);
  }

  if (!confirm(`Reject ${selectedIds.length} selected applicant(s)?`)) {
    return;
  }

  try {
    for (const id of selectedIds) {
      await api(`/recruiter/applications/${id}/status`, {
        method: 'POST',
        body: JSON.stringify({
          status: 'Rejected'
        })
      });
    }

    toast(`${selectedIds.length} applicant(s) rejected successfully.`);

await loadRecruiter();

const selectedJob = document.querySelector('.view-apps[data-id]');
if (selectedJob) {
  await loadApplicants(
    Number(selectedJob.dataset.id),
    selectedJob.dataset.title
  );
}

  } catch (e) {
    toast(e.message, true);
  }
};


async function changeStatus(id,newStatus){
  try{
    await api(`/recruiter/applications/${id}/status`,{
      method:'POST',
      body:JSON.stringify({status:newStatus})
    });

    toast(`Status updated to ${newStatus}.`);

    // Refresh recruiter dashboard
    await loadRecruiter();

    // Refresh current applicants list
    const selectedJob = document.querySelector('.view-apps[data-id]');
    if(selectedJob){
      await loadApplicants(
        Number(selectedJob.dataset.id),
        selectedJob.dataset.title
      );
    }

  }catch(e){
    toast(e.message,true);
  }
}

function showAnalysis(a,cached){$('analysisContent').innerHTML=`<p class="eyebrow">${cached?'CACHED AI ANALYSIS':'AI ANALYSIS'}</p><h2>Candidate-job match</h2><div class="analysis-score">${a.match_score}%</div><p>${escapeHtml(a.summary)}</p><div class="analysis-section"><h4>Matching skills</h4><div class="chips">${a.matching_skills.map(x=>`<span class="chip good">✓ ${escapeHtml(x)}</span>`).join('')||'<span class="muted">None identified</span>'}</div></div><div class="analysis-section"><h4>Missing skills</h4><div class="chips">${a.missing_skills.map(x=>`<span class="chip missing">${escapeHtml(x)}</span>`).join('')||'<span class="muted">None identified</span>'}</div></div><div class="analysis-section"><h4>Experience match</h4><p>${escapeHtml(a.experience_match)}</p></div><div class="analysis-section"><h4>Interview questions</h4>${a.interview_questions.map((q,i)=>`<div class="question">${i+1}. ${escapeHtml(q)}</div>`).join('')}</div><p class="muted" style="margin-top:20px">AI provides a job-related recommendation only. The recruiter makes the final hiring decision.</p>`;$('analysisModal').classList.remove('hidden');}
$('closeModal').onclick=()=> $('analysisModal').classList.add('hidden'); $('analysisModal').onclick=e=>{if(e.target.id==='analysisModal')$('analysisModal').classList.add('hidden');};


async function loadRecruiterStatsOnly(){try{const jobs=await api('/recruiter/jobs');let total=0,s=0,c=0;for(const j of jobs){const a=await api(`/recruiter/jobs/${j.id}/applicants`);total+=a.length;a.forEach(x=>{if(x.analysis){s+=x.analysis.match_score;c++;}})}$('recruiterJobsStat').textContent=jobs.filter(j=>j.is_active).length;$('recruiterApplicantsStat').textContent=total;$('recruiterAvgStat').textContent=c?`${Math.round(s/c)}%`:'—';}catch{}}

$('createJobBtn').onclick=async()=>{try{const payload={title:$('jobTitle').value.trim(),location:$('jobLocation').value.trim(),experience:$('jobExperience').value.trim()||'Not specified',skills:$('jobSkills').value.trim(),description:$('jobDescription').value.trim()};if(!payload.title||!payload.location||!payload.skills||payload.description.length<20)return toast('Please complete the job details.',true);await api('/recruiter/jobs',{method:'POST',body:JSON.stringify(payload)});toast('Job published.');['jobTitle','jobLocation','jobExperience','jobSkills','jobDescription'].forEach(id=>$(id).value='');loadRecruiter();}catch(e){toast(e.message,true);}};
$('refreshRecruiterBtn').onclick=loadRecruiter;

function renderShortlisted(data){const el=$('shortlistedList');el.innerHTML='';data.forEach(a=>{const d=document.createElement('div');d.className='app-card';d.innerHTML=`<h4>${escapeHtml(a.candidate_name)} — ${escapeHtml(a.job_title)}</h4><div class="job-meta">${escapeHtml(a.candidate_email)}</div><span class="status shortlisted">Shortlisted</span>${a.analysis?`<div class="analysis-summary">${a.analysis.match_score}% match · ${escapeHtml(a.analysis.summary)}</div>`:''}`;el.appendChild(d);});}

function escapeHtml(value){return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));}

(async function init(){
  const savedToken = token();
  const savedUser = localStorage.getItem('hireai_user');

  if (!savedToken || !savedUser) return;

  try {
    currentUser = JSON.parse(savedUser);
    showApp();
  } catch {
    localStorage.removeItem('hireai_token');
    localStorage.removeItem('hireai_user');
  }
})();
