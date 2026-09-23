const projectCode = "{{ project_code }}";


    const chat = document.getElementById("chat");
    const messageForm = document.getElementById("messageForm");
    const messageInput = document.getElementById("messageInput");
    const sendButton = document.getElementById("sendButton");
    const chatStatus = document.getElementById("chatStatus");


    /*
     * Escolhe ws:// ou wss:// automaticamente.
     *
     * HTTP  -> ws://
     * HTTPS -> wss://
     */
    const protocol = window.location.protocol === "https:"
        ? "wss:"
        : "ws:";


    const socket = new WebSocket(
        `${protocol}//${window.location.host}/ws/projetos/${projectCode}/chat/`
    );


    /*
     * Quando o WebSocket conectar
     */

    socket.onopen = function () {

        console.log("WebSocket conectado!");

        chatStatus.textContent = "Conectado";
        chatStatus.classList.add("connected");

        sendButton.disabled = false;

        messageInput.focus();
    };


    /*
     * Mensagens recebidas do servidor
     */

    socket.onmessage = function (event) {

        const data = JSON.parse(event.data);


        /*
         * HistÃ³rico enviado quando o chat abre
         */

        if (data.type === "history") {

            chat.innerHTML = "";


            data.messages.forEach(function (message) {

                addMessage(message);

            });


            scrollToBottom();

            return;
        }


        /*
         * Nova mensagem recebida
         */

        if (data.type === "message") {

            addMessage(data);

            scrollToBottom();

        }

    };


    /*
     * WebSocket fechado
     */

    socket.onclose = function () {

        console.log("WebSocket fechado.");

        chatStatus.textContent = "Desconectado";
        chatStatus.classList.remove("connected");
        chatStatus.classList.add("disconnected");

        sendButton.disabled = true;

    };


    /*
     * Erro no WebSocket
     */

    socket.onerror = function (error) {

        console.log("Erro no WebSocket:", error);

        chatStatus.textContent = "Erro na conexÃ£o";

        sendButton.disabled = true;

    };


    /*
     * Envio da mensagem
     */

    messageForm.addEventListener("submit", function (event) {

        event.preventDefault();


        const content = messageInput.value.trim();


        /*
         * NÃ£o envia mensagem vazia
         */

        if (!content) {
            return;
        }


        /*
         * Verifica se o WebSocket estÃ¡ conectado
         */

        if (socket.readyState !== WebSocket.OPEN) {

            console.log(
                "WebSocket nÃ£o estÃ¡ conectado."
            );

            return;
        }


        /*
         * Envia para o Django Channels
         */

        socket.send(
            JSON.stringify({
                message: content
            })
        );


        /*
         * Limpa o input
         */

        messageInput.value = "";

        messageInput.focus();

    });


    /*
     * Adiciona uma mensagem ao chat
     */

    function addMessage(message) {

        /*
         * Remove "Carregando mensagens..."
         */

        const emptyMessage =
            chat.querySelector(".chat-empty");


        if (emptyMessage) {
            emptyMessage.remove();
        }


        /*
         * Container da mensagem
         */

        const messageElement =
            document.createElement("div");

        messageElement.classList.add(
            "chat-message"
        );


        /*
         * CabeÃ§alho
         */

        const headerElement =
            document.createElement("div");

        headerElement.classList.add(
            "chat-message-header"
        );


        /*
         * Nome do usuÃ¡rio
         */

        const usernameElement =
            document.createElement("span");

        usernameElement.classList.add(
            "chat-username"
        );

        usernameElement.textContent =
            message.username;


        /*
         * HorÃ¡rio
         */

        const timeElement =
            document.createElement("span");

        timeElement.classList.add(
            "chat-time"
        );


        const date =
            new Date(message.created_at);


        timeElement.textContent =
            date.toLocaleString("pt-BR");


        /*
         * ConteÃºdo
         */

        const contentElement =
            document.createElement("div");

        contentElement.classList.add(
            "chat-content"
        );


        /*
         * IMPORTANTE:
         *
         * textContent Ã© usado em vez de innerHTML
         * para impedir que uma mensagem contendo
         * HTML/JavaScript seja executada.
         */

        contentElement.textContent =
            message.message;


        /*
         * Monta o cabeÃ§alho
         */

        headerElement.appendChild(
            usernameElement
        );

        headerElement.appendChild(
            timeElement
        );


        /*
         * Monta a mensagem
         */

        messageElement.appendChild(
            headerElement
        );

        messageElement.appendChild(
            contentElement
        );


        /*
         * Adiciona ao chat
         */

        chat.appendChild(
            messageElement
        );

    }


    /*
     * Scroll automÃ¡tico para a Ãºltima mensagem
     */

    function scrollToBottom() {

        chat.scrollTop =
            chat.scrollHeight;

    }

