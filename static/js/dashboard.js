document.addEventListener('DOMContentLoaded', function () {

    const csrfToken =
        document.querySelector(
            '[name=csrfmiddlewaretoken]'
        )?.value;


    const modal =
        document.getElementById('taskModal');


    const openBtn =
        document.getElementById('openTaskModal');


    const closeEls =
        document.querySelectorAll(
            '[data-close-task-modal]'
        );


    const projectSelect =
        document.getElementById('task_project');


    const responsibleSelect =
        document.getElementById(
            'task_responsible'
        );


    const taskCards =
        document.querySelectorAll(
            '.kanban-task'
        );


    const columns =
        document.querySelectorAll(
            '.kanban-column'
        );


    const tdModal =
        document.getElementById(
            'taskDistributionModal'
        );


    const tdOpenBtns =
        document.querySelectorAll(
            '.open-td-modal'
        );


    const tdCloseEls =
        document.querySelectorAll(
            '[data-close-td-modal]'
        );


    const tdTasksInput =
        document.getElementById(
            'tdTasksInput'
        );


    const tdGenerateBtn =
        document.getElementById(
            'tdGenerateBtn'
        );


    const tdConfirmBtn =
        document.getElementById(
            'tdConfirmBtn'
        );


    const tdSuggestionResults =
        document.getElementById(
            'tdSuggestionResults'
        );


    let tdCurrentProjectId = null;


    tdOpenBtns.forEach(function (btn) {

        btn.addEventListener(
            'click',
            function () {

                tdCurrentProjectId =
                    btn.dataset.projectId;


                document.getElementById(
                    'tdModalTitle'
                ).textContent =
                    `Sugerir tarefas â€” ${btn.dataset.projectTitle}`;


                tdTasksInput.value = '';

                tdSuggestionResults.innerHTML = '';

                tdConfirmBtn.classList.add('td-confirm-hidden');
                tdConfirmBtn.classList.remove('td-confirm-visible');


                tdModal.classList.add('open');

                tdModal.setAttribute(
                    'aria-hidden',
                    'false'
                );

            }
        );

    });


    tdCloseEls.forEach(function (el) {

        el.addEventListener(
            'click',
            function () {

                tdModal.classList.remove('open');

                tdModal.setAttribute(
                    'aria-hidden',
                    'true'
                );

            }
        );

    });


    tdGenerateBtn.addEventListener(
        'click',
        function () {

            const linhas =
                tdTasksInput.value
                    .split('\n')
                    .map(l => l.trim())
                    .filter(Boolean);


            if (!linhas.length) {

                tdSuggestionResults.innerHTML =
                    '<div class="td-feedback-error">Digite ao menos uma tarefa.</div>';

                return;

            }


            tdGenerateBtn.disabled = true;

            tdGenerateBtn.textContent =
                'Analisando...';


            tdSuggestionResults.innerHTML =
                    '<div class="td-feedback-muted">Buscando membros e gerando sugestão...</div>';


            const formData =
                new FormData();


            linhas.forEach(
                desc =>
                    formData.append(
                        'task_description',
                        desc
                    )
            );


            fetch(
                `/tarefas/${tdCurrentProjectId}/sugerir-distribuicao/`,
                {
                    method: 'POST',

                    headers: {
                        'X-CSRFToken':
                            csrfToken
                    },

                    body: formData
                }
            )
            .then(res => res.json())
            .then(data => {

                if (
                    !data.tasks ||
                    !data.tasks.length
                ) {

                    tdSuggestionResults.innerHTML =
                        `<div class="td-feedback-error">${data.error || 'Não foi possível gerar sugestão.'}</div>`;

                    return;

                }


                const assignPorId = {};


                (data.assignments || [])
                    .forEach(
                        a =>
                            assignPorId[
                                a.temp_id
                            ] = a
                    );


                tdSuggestionResults.innerHTML =
                    data.tasks
                        .map(task => {

                            const assign =
                                assignPorId[
                                    task.temp_id
                                ];


                            return `

                                <div class="td-suggestion-card">

                                    <div class="td-suggestion-description">
                                        ${task.description}
                                    </div>

                                    <div class="td-suggestion-assignment ${assign ? 'assigned' : 'unassigned'}">
                                        ${
                                            assign
                                                ? '-> Responsável sugerido (ID ' + assign.assigned_user_id + ')'
                                                : 'Sem sugestão - atribuir manualmente depois'
                                        }
                                    </div>

                                </div>

                            `;

                        })
                        .join('');


                tdConfirmBtn.classList.remove('td-confirm-hidden');
                tdConfirmBtn.classList.add('td-confirm-visible');

            })
            .catch(() => {

                tdSuggestionResults.innerHTML =
                    '<div class="td-feedback-error">Erro ao gerar sugestão.</div>';

            })
            .finally(() => {

                tdGenerateBtn.disabled = false;

                tdGenerateBtn.textContent =
                    'Gerar sugestÃ£o';

            });

        }
    );


    tdConfirmBtn.addEventListener(
        'click',
        function () {

            tdConfirmBtn.disabled = true;

            tdConfirmBtn.textContent =
                'Criando...';


            fetch(
                `/tarefas/${tdCurrentProjectId}/confirmar-distribuicao/`,
                {
                    method: 'POST',

                    headers: {
                        'X-CSRFToken':
                            csrfToken
                    }
                }
            )
            .then(res => res.json())
            .then(data => {

                if (data.status === 'success') {

                    location.reload();

                } else {

                    alert(
                        'Erro: ' +
                        (
                            data.error ||
                            'nÃ£o foi possÃ­vel criar as tarefas.'
                        )
                    );

                }

            })
            .finally(() => {

                tdConfirmBtn.disabled = false;

                tdConfirmBtn.textContent =
                    'Confirmar e criar tarefas';

            });

        }
    );


    function moveTask(
        taskId,
        newStatus
    ) {

        if (!taskId || !newStatus) {
            return;
        }


        fetch(
            `/tarefas/${taskId}/status/`,
            {
                method: 'POST',

                headers: {
                    'Content-Type':
                        'application/x-www-form-urlencoded; charset=UTF-8',

                    'X-CSRFToken':
                        csrfToken,

                    'X-Requested-With':
                        'XMLHttpRequest',
                },

                body: new URLSearchParams({
                    status: newStatus
                })
            }
        )
        .then(response =>
            response.json()
        )
        .then(data => {

            if (!data.success) {

                console.error(
                    data.error ||
                    'Erro ao mover tarefa'
                );

                return;

            }


            const taskElement =
                document.querySelector(
                    `.kanban-task[data-task-id="${taskId}"]`
                );


            if (taskElement) {

                taskElement.dataset.status =
                    newStatus;

            }


            location.reload();

        })
        .catch(error => {

            console.error(
                'Erro ao mover tarefa:',
                error
            );

        });

    }


    taskCards.forEach(
        function (taskCard) {

            taskCard.addEventListener(
                'dragstart',
                function () {

                    taskCard.classList.add(
                        'dragging'
                    );

                    taskCard.setAttribute(
                        'data-dragging',
                        'true'
                    );

                }
            );


            taskCard.addEventListener(
                'dragend',
                function () {

                    taskCard.classList.remove(
                        'dragging'
                    );

                    taskCard.removeAttribute(
                        'data-dragging'
                    );

                }
            );

        }
    );


    columns.forEach(
        function (column) {

            column.addEventListener(
                'dragover',
                function (event) {

                    event.preventDefault();

                    column.classList.add(
                        'drag-over'
                    );

                }
            );


            column.addEventListener(
                'dragleave',
                function () {

                    column.classList.remove(
                        'drag-over'
                    );

                }
            );


            column.addEventListener(
                'drop',
                function (event) {

                    event.preventDefault();

                    column.classList.remove(
                        'drag-over'
                    );


                    const draggedTask =
                        document.querySelector(
                            '.kanban-task[data-dragging="true"]'
                        );


                    if (!draggedTask) {
                        return;
                    }


                    const taskId =
                        draggedTask.dataset.taskId;


                    const newStatus =
                        column.dataset.status ||
                        column.getAttribute(
                            'data-status'
                        );


                    if (
                        !taskId ||
                        !newStatus
                    ) {
                        return;
                    }


                    const targetContainer =
                        column.querySelector(
                            '.drop-zone-placeholder'
                        );


                    if (targetContainer) {

                        column.insertBefore(
                            draggedTask,
                            targetContainer
                        );

                    } else {

                        column.appendChild(
                            draggedTask
                        );

                    }


                    moveTask(
                        taskId,
                        newStatus
                    );

                }
            );

        }
    );


    const projectMembers = JSON.parse(document.getElementById('projectMembersData').textContent);


    function populateResponsibleOptions(
        projectId
    ) {

        responsibleSelect.innerHTML =
            '<option value="">Selecione um membro do projeto</option>';


        const members =
            projectMembers[projectId] || [];


        if (!members.length) {

            const owner = JSON.parse(document.getElementById('dashboardData').textContent);
            const ownerOption = document.createElement('option');
            ownerOption.value = owner.id;
            ownerOption.textContent = owner.name;
            responsibleSelect.appendChild(ownerOption);
            return;

        }


        members.forEach(
            function (member) {

                const option =
                    document.createElement(
                        'option'
                    );


                option.value =
                    member.value;


                option.textContent =
                    member.label;


                responsibleSelect.appendChild(
                    option
                );

            }
        );

    }


    if (
        projectSelect &&
        responsibleSelect
    ) {

        projectSelect.addEventListener(
            'change',
            function () {

                populateResponsibleOptions(
                    this.value
                );

            }
        );


        if (projectSelect.value) {

            populateResponsibleOptions(
                projectSelect.value
            );

        }

    }


    if (
        modal &&
        openBtn
    ) {

        openBtn.addEventListener(
            'click',
            function () {

                modal.classList.add(
                    'open'
                );

                modal.setAttribute(
                    'aria-hidden',
                    'false'
                );

            }
        );


        closeEls.forEach(
            function (el) {

                el.addEventListener(
                    'click',
                    function () {

                        modal.classList.remove(
                            'open'
                        );

                        modal.setAttribute(
                            'aria-hidden',
                            'true'
                        );

                    }
                );

            }
        );


        document.addEventListener(
            'keydown',
            function (event) {

                if (
                    event.key === 'Escape' &&
                    modal.classList.contains('open')
                ) {

                    modal.classList.remove(
                        'open'
                    );

                    modal.setAttribute(
                        'aria-hidden',
                        'true'
                    );

                }

            }
        );

    }

});

