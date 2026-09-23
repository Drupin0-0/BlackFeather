const memberSearch = document.getElementById('memberSearch');
const memberSearchResults = document.getElementById('memberSearchResults');
const selectedMembersBox = document.getElementById('selectedMembers');
const projectForm = document.getElementById('projectForm');
const suggestionBox = document.getElementById('suggestionBox');
const suggestionResults = document.getElementById('suggestionResults');
const suggestMembersBtn = document.getElementById('suggestMembersBtn');
const selectedMembers = new Map();

function addHiddenMemberInputs() {
    projectForm.querySelectorAll('input[name="members"]').forEach(input => input.remove());
    selectedMembers.forEach(member => {
        const input = document.createElement('input');
        input.type = 'hidden';
        input.name = 'members';
        input.value = member.id;
        projectForm.appendChild(input);
    });
}

function renderSelectedMembers() {
    selectedMembersBox.innerHTML = '';
    if (!selectedMembers.size) {
        selectedMembersBox.innerHTML = '<span class="selected-members-empty">Nenhum membro selecionado.</span>';
        addHiddenMemberInputs();
        return;
    }
    selectedMembers.forEach(member => {
        const chip = document.createElement('div');
        chip.className = 'member-chip';
        const label = document.createTextNode(member.name || 'Nome não informado');
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.textContent = '×';
        removeBtn.addEventListener('click', function() {
            selectedMembers.delete(member.id);
            renderSelectedMembers();
        });
        chip.appendChild(label);
        chip.appendChild(removeBtn);
        selectedMembersBox.appendChild(chip);
    });
    addHiddenMemberInputs();
}

function renderUserResults(users) {
    memberSearchResults.innerHTML = '';
    if (!users.length) {
        memberSearchResults.innerHTML = '<div class="feedback-empty">Nenhum usuário encontrado.</div>';
        return;
    }
    users.forEach(user => {
        const card = document.createElement('div');
        card.className = 'member-result';
        const info = document.createElement('div');
        info.className = 'member-result-info';
        const name = document.createElement('div');
        name.className = 'member-result-name';
        name.textContent = user.name || 'Nome não informado';
        const email = document.createElement('div');
        email.className = 'member-result-email';
        email.textContent = user.email;
        const skills = document.createElement('div');
        skills.className = 'member-result-skills';
        skills.textContent = (user.skills || []).slice(0, 3).join(', ') || 'Sem skills cadastradas';
        info.append(name, email, skills);
        const addBtn = document.createElement('button');
        const alreadySelected = selectedMembers.has(user.id);
        addBtn.type = 'button';
        addBtn.textContent = alreadySelected ? 'Adicionado' : 'Adicionar';
        addBtn.disabled = alreadySelected;
        addBtn.addEventListener('click', function() {
            if (!selectedMembers.has(user.id)) {
                selectedMembers.set(user.id, user);
                renderSelectedMembers();
                renderUserResults([]);
            }
        });
        card.append(info, addBtn);
        memberSearchResults.appendChild(card);
    });
}

memberSearch.addEventListener('input', function() {
    const query = memberSearch.value.trim();
    if (!query) { memberSearchResults.innerHTML = ''; return; }
    fetch(`/accounts/buscar-usuarios/?q=${encodeURIComponent(query)}`)
        .then(response => { if (!response.ok) throw new Error(); return response.json(); })
        .then(data => renderUserResults(data.results || []))
        .catch(() => { memberSearchResults.innerHTML = '<div class="feedback-error">Erro ao buscar usuários.</div>'; });
});

suggestMembersBtn.addEventListener('click', function() {
    const title = document.getElementById('title').value.trim();
    const description = document.getElementById('description').value.trim();
    const members = Array.from(selectedMembers.keys());
    suggestionBox.classList.add('suggestion-visible');
    suggestionResults.innerHTML = '<div class="feedback-muted">Analisando membros e projeto...</div>';
    suggestMembersBtn.disabled = true;
    suggestMembersBtn.textContent = 'Analisando...';
    if (!title) { suggestionResults.innerHTML = '<div class="feedback-error">Preencha o nome do projeto antes de sugerir.</div>'; suggestMembersBtn.disabled = false; suggestMembersBtn.textContent = '✨ Sugerir membros com IA'; return; }
    if (!members.length) { suggestionResults.innerHTML = '<div class="feedback-error">Selecione pelo menos um membro para a sugestão.</div>'; suggestMembersBtn.disabled = false; suggestMembersBtn.textContent = '✨ Sugerir membros com IA'; return; }
    const formData = new FormData();
    formData.append('title', title); formData.append('description', description);
    members.forEach(memberId => formData.append('members', memberId));
    fetch(projectForm.dataset.suggestUrl, { method: 'POST', headers: { 'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value }, body: formData })
        .then(response => { if (!response.ok) throw new Error(); return response.json(); })
        .then(data => {
            if (!data.suggestions || !data.suggestions.length) { suggestionResults.innerHTML = '<div class="feedback-error">Não foi possível gerar sugestão com os dados atuais.</div>'; return; }
            suggestionResults.innerHTML = data.suggestions.map(item => {
                const skills = (item.skills || []).slice(0, 4).join(', ') || 'Sem skills cadastradas';
                const matches = (item.matched_skills || []).length ? `Corresponde a: ${item.matched_skills.join(', ')}` : 'Sem correspondência direta';
                return `<div class="ai-suggestion"><div class="ai-suggestion-header"><strong>${item.name || 'Nome não informado'}</strong><span class="ai-suggestion-score">Score ${item.score || 0}</span></div><div class="ai-suggestion-email">${item.email}</div><div class="ai-suggestion-skills">${skills}</div><div class="ai-suggestion-matches">${matches}</div></div>`;
            }).join('');
        })
        .catch(() => { suggestionResults.innerHTML = '<div class="feedback-error">Erro ao gerar sugestão com a IA.</div>'; })
        .finally(() => { suggestMembersBtn.disabled = false; suggestMembersBtn.textContent = '✨ Sugerir membros com IA'; });
});

renderSelectedMembers();
