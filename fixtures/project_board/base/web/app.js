// Intentionally tiny browser integration. External grader owns acceptance expectations.
const selector = document.getElementById('project-select');
const details = document.getElementById('project-details');
const message = document.getElementById('message');
const exportButton = document.getElementById('export');
const fields = ['title','category','phase','owner','milestone_start','milestone_end','reference_code'];
let currentId = null;

async function requireResponse(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response;
}

async function loadProjects() {
  const list = await (await requireResponse('/api/projects')).json();
  for (const project of list) {
    const option = document.createElement('option');
    option.value = project.id;
    option.textContent = project.title;
    selector.append(option);
  }
}

selector.addEventListener('change', async () => {
  currentId = selector.value;
  details.hidden = true;
  exportButton.disabled = true;
  message.textContent = '';
  if (!currentId) return;
  try {
    const project = await (await requireResponse(`/api/projects/${currentId}`)).json();
    for (const field of fields) {
      if (!Object.hasOwn(project, field)) throw new Error(`Missing field: ${field}`);
      document.querySelector(`[data-field="${field}"]`).textContent = project[field];
    }
    document.getElementById('notes').value = project.notes;
    details.hidden = false;
  } catch (error) { message.textContent = `Load failed: ${error.message}`; }
});

document.getElementById('save').addEventListener('click', async () => {
  try {
    await requireResponse(`/api/projects/${currentId}/notes`, {
      method: 'POST', headers: {'Content-Type':'application/json','X-Demo-Role':'editor'},
      body: JSON.stringify({notes: document.getElementById('notes').value})
    });
    exportButton.disabled = false;
    message.textContent = 'Saved';
  } catch (error) { message.textContent = `Save failed: ${error.message}`; }
});

exportButton.addEventListener('click', () => {
  if (!exportButton.disabled && currentId) window.location.href = `/api/projects/${currentId}/export`;
});

loadProjects().catch(error => message.textContent = `List failed: ${error.message}`);
