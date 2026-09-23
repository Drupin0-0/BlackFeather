const profileSetup = document.getElementById('profileSetup');
const existingSkills = (profileSetup.dataset.existingSkills || '')
    .split(',')
    .filter(Boolean);

document.querySelectorAll('input[name="skills"]').forEach(input => {
    if (existingSkills.includes(input.value)) input.checked = true;
});
