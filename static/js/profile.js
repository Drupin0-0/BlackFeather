let selectedSkillOption = null;
let currentEditingSkillName = null;
let currentEditingSkillIcon = null;

function triggerPhotoUpload() {
    document.getElementById('photoInput').click();
}

function previewImage(event) {
    const file = event.target.files[0];
    if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
            document.getElementById('avatarPreview').src = e.target.result;
        };
        reader.readAsDataURL(file);
    }
}

function openModal(modalId) {
    document.getElementById(modalId).classList.add('active');
}

function closeModal(modalId) {
    document.getElementById(modalId).classList.remove('active');
}

function openManageSkillsModal() {
    const manageList = document.getElementById('manageSkillsList');
    manageList.innerHTML = '';
    const skills = document.querySelectorAll('#userSkillsList .skill-chip');

    if (skills.length === 0) {
        manageList.innerHTML = '<p class="skill-empty-state">Nenhuma skill adicionada.</p>';
    } else {
        skills.forEach(skill => {
            const name = skill.getAttribute('data-skill-name');
            const icon = skill.getAttribute('data-skill-icon');
            const item = document.createElement('div');
            item.className = 'manage-skill-item';
            item.innerHTML = `
                <div class="skill-info-left">
                    <i class="${icon}"></i>
                    <span>${name}</span>
                </div>
                <button type="button" class="btn-edit-skill" onclick="openEditSkillModal('${name}', '${icon}')">
                    <i class="fa-solid fa-pen"></i> Editar
                </button>
            `;
            manageList.appendChild(item);
        });
    }

    openModal('manageSkillsModal');
}

function openAddSkillModal() {
    selectedSkillOption = null;
    document.querySelectorAll('#availableSkillsList .skill-option').forEach(opt => {
        opt.classList.remove('selected');
    });
    openModal('addSkillModal');
}

function selectSkillOption(element, name, icon) {
    document.querySelectorAll('#availableSkillsList .skill-option').forEach(opt => {
        opt.classList.remove('selected');
    });
    element.classList.add('selected');
    selectedSkillOption = { name, icon };
}

function confirmAddSkill() {
    if (!selectedSkillOption) return;
    const existingSkills = Array.from(document.querySelectorAll('#userSkillsList .skill-chip'))
        .map(chip => chip.getAttribute('data-skill-name'));

    if (existingSkills.includes(selectedSkillOption.name)) {
        closeModal('addSkillModal');
        return;
    }

    const skillsContainer = document.getElementById('userSkillsList');
    const newChip = document.createElement('div');
    newChip.className = 'skill-chip';
    newChip.setAttribute('data-skill-name', selectedSkillOption.name);
    newChip.setAttribute('data-skill-icon', selectedSkillOption.icon);
    newChip.innerHTML = `
        <i class="${selectedSkillOption.icon}"></i>
        <span>${selectedSkillOption.name}</span>
    `;
    skillsContainer.appendChild(newChip);
    closeModal('addSkillModal');
}

function openEditSkillModal(name, icon) {
    currentEditingSkillName = name;
    currentEditingSkillIcon = icon;
    document.getElementById('editSkillName').innerText = name;
    document.getElementById('editSkillIcon').className = icon;
    closeModal('manageSkillsModal');
    openModal('editSkillModal');
}

function openConfirmRemoveModal() {
    closeModal('editSkillModal');
    openModal('confirmRemoveModal');
}

function confirmRemoveSkill() {
    const skills = document.querySelectorAll('#userSkillsList .skill-chip');
    skills.forEach(skill => {
        if (skill.getAttribute('data-skill-name') === currentEditingSkillName) {
            skill.remove();
        }
    });
    closeModal('confirmRemoveModal');
    currentEditingSkillName = null;
    currentEditingSkillIcon = null;
}
