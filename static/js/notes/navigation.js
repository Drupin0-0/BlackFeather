(function () {
    'use strict';

    const button = document.getElementById('projectMenuToggle');
    const navigation = document.getElementById('projectNavigation');
    const userIdElement = document.getElementById('notes-user-id');
    if (!button || !navigation || !userIdElement || button.dataset.bound === 'true') {
        return;
    }
    button.dataset.bound = 'true';

    const userId = JSON.parse(userIdElement.textContent);
    const storageKey = 'sincrow:project-navigation:' + userId;

    function update(collapsed, persist) {
        navigation.classList.toggle('collapsed', collapsed);
        button.textContent = collapsed ? '↑' : '↓';
        button.title = collapsed ? 'Abrir barra' : 'Minimizar barra';
        button.setAttribute('aria-label', button.title);
        button.setAttribute('aria-expanded', String(!collapsed));
        if (persist) {
            try {
                window.localStorage.setItem(storageKey, collapsed ? 'collapsed' : 'expanded');
            } catch (error) {
                return;
            }
        }
    }

    let collapsed = false;
    try {
        collapsed = window.localStorage.getItem(storageKey) === 'collapsed';
    } catch (error) {
        collapsed = false;
    }
    update(collapsed, false);
    button.addEventListener('click', function () {
        update(!navigation.classList.contains('collapsed'), true);
    });
}());
