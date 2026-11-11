(function () {
    'use strict';

    const root = document.getElementById('notesRoot');
    const workArea = document.getElementById('notesWorkArea');
    const world = document.getElementById('notesWorld');
    const toolbar = document.getElementById('notesToolbar');
    const editor = window.notesEditor;
    if (!root || !workArea || !world || !toolbar || !editor || !window.NotesInkUtils) {
        return;
    }

    const utils = window.NotesInkUtils;
    const svgNamespace = 'http://www.w3.org/2000/svg';
    const CUSTOM_SLOTS = 5;
    const userId = JSON.parse(document.getElementById('notes-user-id').textContent);
    const preferenceKey = 'sincrow:notes:ink:' + userId;
    const paletteKeys = {
        ink: 'sincrow:notes:custom-colors:ink:' + userId,
        text: 'sincrow:notes:custom-colors:text:' + userId,
    };
    const legacyPaletteKey = 'sincrow:notes:palette:' + userId;
    const colorInput = document.getElementById('notesInkCustomColor');
    const textColorInput = document.getElementById('notesCustomColor');
    const widthInput = document.getElementById('notesInkWidth');
    const widthValue = document.getElementById('notesInkWidthValue');
    const widthPreview = document.getElementById('notesInkWidthPreview');
    const widthLabel = document.getElementById('notesSizeLabel');
    const sizeTrigger = toolbar.querySelector('[data-size-toggle]');
    const sizePopover = document.getElementById('notesSizePopover');
    const shapesTrigger = toolbar.querySelector('[data-shape-toggle]');
    const message = document.getElementById('notesInkMessage');
    const svg = document.createElementNS(svgNamespace, 'svg');
    svg.classList.add('notes-ink');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('preserveAspectRatio', 'none');
    const eraserCursor = document.createElement('div');
    eraserCursor.className = 'notes-eraser-cursor';
    eraserCursor.hidden = true;
    const selectionBox = document.createElement('div');
    selectionBox.className = 'notes-selection-box';
    selectionBox.hidden = true;

    const preferences = { color: 'auto', width: 4, eraserSize: 20, textColor: '#ffffff' };
    const state = {
        tool: editor.getTool(),
        selectedShape: 'rectangle',
        activePointerId: null,
        active: null,
        nextStrokeZ: 1,
        pathsById: new Map(),
        selectedIds: new Set(),
        animationFrame: null,
        messageTimer: null,
        customColors: { ink: [], text: [] },
        marqueeIds: new Set(),
        itemBounds: new Map(),
    };

    toolbar.parentElement.append(sizePopover);

    const shapeDefinitions = [
        ['line', 'Linha'],
        ['curve', 'Curva'],
        ['ellipse', 'Elipse'],
        ['square', 'Quadrado'],
        ['rectangle', 'Retângulo'],
        ['roundedRectangle', 'Retângulo arredondado'],
        ['rightTriangle', 'Triângulo retângulo'],
        ['triangle', 'Triângulo'],
        ['diamond', 'Losango'],
        ['pentagon', 'Pentágono'],
        ['hexagon', 'Hexágono'],
        ['parallelogram', 'Paralelogramo'],
        ['trapezoid', 'Trapézio'],
        ['rightArrow', 'Seta para a direita'],
        ['leftArrow', 'Seta para a esquerda'],
        ['upArrow', 'Seta para cima'],
        ['downArrow', 'Seta para baixo'],
        ['fourPointStar', 'Estrela de quatro pontas'],
        ['fivePointStar', 'Estrela de cinco pontas'],
        ['sixPointStar', 'Estrela de seis pontas'],
        ['eightPointStar', 'Estrela de oito pontas'],
        ['speechBubble', 'Balão de fala'],
        ['thoughtBubble', 'Balão de pensamento'],
        ['heart', 'Coração'],
    ];
    const shapesPopover = document.createElement('div');
    shapesPopover.className = 'notes-shapes-popover';
    shapesPopover.id = 'notesShapesPopover';
    shapesPopover.setAttribute('role', 'group');
    shapesPopover.setAttribute('aria-label', 'Opções de formas');
    shapesPopover.hidden = true;
    toolbar.parentElement.append(shapesPopover);

    function shapePoints(name, start, end) {
        let left = Math.min(start.x, end.x);
        let right = Math.max(start.x, end.x);
        let top = Math.min(start.y, end.y);
        let bottom = Math.max(start.y, end.y);
        if (name === 'square') {
            const side = Math.max(right - left, bottom - top);
            right = left + side * (end.x >= start.x ? 1 : -1);
            bottom = top + side * (end.y >= start.y ? 1 : -1);
            left = Math.min(start.x, right);
            right = Math.max(start.x, right);
            top = Math.min(start.y, bottom);
            bottom = Math.max(start.y, bottom);
        }
        const width = Math.max(1, right - left);
        const height = Math.max(1, bottom - top);
        const point = function (x, y) { return [left + x * width, top + y * height]; };
        const polygon = function (vertices) {
            const coords = vertices.map(function (vertex) { return point(vertex[0], vertex[1]); });
            coords.push(coords[0]);
            return coords;
        };
        const regularPolygon = function (sides, rotation) {
            const vertices = [];
            for (let index = 0; index < sides; index += 1) {
                const angle = -Math.PI / 2 + rotation + index * Math.PI * 2 / sides;
                vertices.push([0.5 + Math.cos(angle) * 0.48, 0.5 + Math.sin(angle) * 0.48]);
            }
            return polygon(vertices);
        };
        let points;
        if (name === 'line') {
            points = [[start.x, start.y], [end.x, end.y]];
        } else if (name === 'curve') {
            points = [];
            for (let index = 0; index <= 24; index += 1) {
                const t = index / 24;
                points.push([
                    left + t * width,
                    top + height * (0.5 - 0.42 * Math.sin(t * Math.PI)),
                ]);
            }
        } else if (name === 'ellipse' || name === 'thoughtBubble') {
            const count = 48;
            points = [];
            for (let index = 0; index <= count; index += 1) {
                const angle = index * Math.PI * 2 / count;
                points.push([
                    left + width * (0.5 + Math.cos(angle) * 0.5),
                    top + height * (0.5 + Math.sin(angle) * 0.5),
                ]);
            }
            if (name === 'thoughtBubble') {
                points = points.concat([
                    [left + width * 0.2, top + height * 0.82],
                    [left + width * 0.14, top + height * 0.94],
                    [left + width * 0.29, top + height * 0.9],
                    points[0],
                ]);
            }
        } else if (name === 'rectangle' || name === 'square') {
            points = polygon([[0, 0], [1, 0], [1, 1], [0, 1]]);
        } else if (name === 'roundedRectangle') {
            points = [];
            const radius = 0.14;
            const corners = [
                [1 - radius, radius, -Math.PI / 2],
                [1 - radius, 1 - radius, 0],
                [radius, 1 - radius, Math.PI / 2],
                [radius, radius, Math.PI],
            ];
            corners.forEach(function (corner) {
                for (let index = 0; index <= 8; index += 1) {
                    const angle = corner[2] + index * Math.PI / 16;
                    points.push(point(
                        corner[0] + Math.cos(angle) * radius,
                        corner[1] + Math.sin(angle) * radius,
                    ));
                }
            });
            points.push(points[0]);
        } else if (name === 'rightTriangle') {
            points = polygon([[0, 0], [0, 1], [1, 1]]);
        } else if (name === 'triangle') {
            points = polygon([[0.5, 0], [1, 1], [0, 1]]);
        } else if (name === 'diamond') {
            points = polygon([[0.5, 0], [1, 0.5], [0.5, 1], [0, 0.5]]);
        } else if (name === 'pentagon') {
            points = regularPolygon(5, 0);
        } else if (name === 'hexagon') {
            points = regularPolygon(6, 0);
        } else if (name === 'parallelogram') {
            points = polygon([[0.25, 0], [1, 0], [0.75, 1], [0, 1]]);
        } else if (name === 'trapezoid') {
            points = polygon([[0.2, 0], [0.8, 0], [1, 1], [0, 1]]);
        } else if (/^(right|left|up|down)Arrow$/.test(name)) {
            const vertices = [
                [0, 0.34], [0.62, 0.34], [0.62, 0.05], [1, 0.5],
                [0.62, 0.95], [0.62, 0.66], [0, 0.66],
            ];
            if (name === 'leftArrow') {
                vertices.forEach(function (vertex) { vertex[0] = 1 - vertex[0]; });
            } else if (name === 'upArrow' || name === 'downArrow') {
                vertices.forEach(function (vertex) {
                    const x = vertex[0];
                    vertex[0] = vertex[1];
                    vertex[1] = name === 'upArrow' ? 1 - x : x;
                });
            }
            points = polygon(vertices);
        } else if (/^(four|five|six|eight)PointStar$/.test(name)) {
            const tipsByName = {
                fourPointStar: 4,
                fivePointStar: 5,
                sixPointStar: 6,
                eightPointStar: 8,
            };
            const tips = tipsByName[name];
            const vertices = [];
            for (let index = 0; index < tips * 2; index += 1) {
                const angle = -Math.PI / 2 + index * Math.PI / tips;
                const radius = index % 2 === 0 ? 0.49 : 0.2;
                vertices.push([
                    0.5 + Math.cos(angle) * radius,
                    0.5 + Math.sin(angle) * radius,
                ]);
            }
            points = polygon(vertices);
        } else if (name === 'speechBubble') {
            points = polygon([[0, 0], [1, 0], [1, 0.72], [0.68, 0.72], [0.48, 1], [0.48, 0.72], [0, 0.72]]);
        } else if (name === 'heart') {
            points = [];
            for (let index = 0; index <= 48; index += 1) {
                const angle = index * Math.PI * 2 / 48;
                const x = 16 * Math.pow(Math.sin(angle), 3);
                const y = 13 * Math.cos(angle) - 5 * Math.cos(2 * angle) -
                    2 * Math.cos(3 * angle) - Math.cos(4 * angle);
                points.push([left + (x + 17) / 34 * width, top + (18 - y) / 34 * height]);
            }
        }
        return points ? points.reduce(function (flat, item) {
            flat.push(item[0], item[1]);
            return flat;
        }, []) : [];
    }

    function positionShapesPopover() {
        const rect = shapesTrigger.getBoundingClientRect();
        const width = shapesPopover.offsetWidth;
        const height = shapesPopover.offsetHeight;
        shapesPopover.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)) + 'px';
        shapesPopover.style.top = Math.max(8, rect.top - height - 6) + 'px';
    }

    function renderShapeOptions() {
        shapesPopover.replaceChildren();
        shapeDefinitions.forEach(function (definition) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'notes-shape-option';
            button.dataset.shape = definition[0];
            button.title = definition[1];
            button.setAttribute('aria-label', definition[1]);
            button.setAttribute('aria-pressed', String(state.selectedShape === definition[0]));
            button.classList.toggle('is-active', state.selectedShape === definition[0]);
            const icon = document.createElementNS(svgNamespace, 'svg');
            icon.setAttribute('viewBox', '0 0 24 24');
            icon.setAttribute('aria-hidden', 'true');
            const path = document.createElementNS(svgNamespace, 'path');
            path.setAttribute('d', utils.pathData(shapePoints(definition[0], { x: 3, y: 3 }, { x: 21, y: 21 })));
            icon.append(path);
            button.append(icon);
            shapesPopover.append(button);
        });
    }

    renderShapeOptions();
    shapesTrigger.addEventListener('click', function () {
        shapesPopover.hidden = !shapesPopover.hidden;
        shapesTrigger.setAttribute('aria-expanded', String(!shapesPopover.hidden));
        if (!shapesPopover.hidden) {
            positionShapesPopover();
        }
    });
    shapesPopover.addEventListener('click', function (event) {
        const option = event.target.closest('[data-shape]');
        if (!option) {
            return;
        }
        state.selectedShape = option.dataset.shape;
        shapesPopover.hidden = true;
        shapesTrigger.setAttribute('aria-expanded', 'false');
        shapesTrigger.title = 'Formas: ' + option.title;
        shapesTrigger.setAttribute('aria-label', 'Formas: ' + option.title);
        editor.setTool('shape');
        renderShapeOptions();
    });
    document.addEventListener('pointerdown', function (event) {
        if (!shapesPopover.hidden && !shapesPopover.contains(event.target) &&
            !shapesTrigger.contains(event.target)) {
            shapesPopover.hidden = true;
            shapesTrigger.setAttribute('aria-expanded', 'false');
        }
    });
    window.addEventListener('resize', function () {
        if (!shapesPopover.hidden) {
            positionShapesPopover();
        }
    });
    toolbar.addEventListener('scroll', function () {
        if (!shapesPopover.hidden) {
            positionShapesPopover();
        }
    }, true);

    function validColor(color) {
        return typeof color === 'string' && /^#[0-9a-fA-F]{6}$/.test(color);
    }

    function resolvedInkColor() {
        const value = getComputedStyle(document.querySelector('.notes-editor'))
            .getPropertyValue('--notes-ink-default').trim();
        if (validColor(value)) {
            return value;
        }
        const channels = value.match(/^rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)/i);
        return channels
            ? '#' + channels.slice(1, 4).map(function (channel) {
                return Number(channel).toString(16).padStart(2, '0');
            }).join('')
            : '#e6edf7';
    }

    function showMessage(text) {
        message.textContent = text;
        message.hidden = false;
        if (state.messageTimer) {
            window.clearTimeout(state.messageTimer);
        }
        state.messageTimer = window.setTimeout(function () {
            message.hidden = true;
        }, 5000);
    }

    function clearMessage() {
        if (state.messageTimer) {
            window.clearTimeout(state.messageTimer);
            state.messageTimer = null;
        }
        message.hidden = true;
    }

    function savePreferences() {
        try {
            window.localStorage.setItem(preferenceKey, JSON.stringify(preferences));
        } catch (error) {
            return;
        }
    }

    function loadPreferences() {
        try {
            const saved = JSON.parse(window.localStorage.getItem(preferenceKey) || '{}');
            if (saved && (saved.color === 'auto' || validColor(saved.color))) {
                preferences.color = saved.color;
            }
            if (saved && Number.isInteger(saved.width) && saved.width >= 1 && saved.width <= 40) {
                preferences.width = saved.width;
            }
            if (saved && Number.isInteger(saved.eraserSize) &&
                saved.eraserSize >= 4 && saved.eraserSize <= 80) {
                preferences.eraserSize = saved.eraserSize;
            }
            if (saved && validColor(saved.textColor)) {
                preferences.textColor = saved.textColor;
            }
        } catch (error) {
            preferences.color = 'auto';
            preferences.width = 4;
            preferences.eraserSize = 20;
            preferences.textColor = '#ffffff';
        }
        loadCustomColors();
    }

    function normalizeColors(value) {
        if (!Array.isArray(value)) {
            return [];
        }
        const colors = [];
        value.forEach(function (color) {
            if (validColor(color) && !colors.includes(color.toLowerCase()) &&
                colors.length < CUSTOM_SLOTS) {
                colors.push(color.toLowerCase());
            }
        });
        return colors;
    }

    function readColorList(key) {
        try {
            const raw = window.localStorage.getItem(key);
            return raw === null ? null : normalizeColors(JSON.parse(raw));
        } catch (error) {
            return [];
        }
    }

    function loadCustomColors() {
        try {
            const legacyRaw = window.localStorage.getItem(legacyPaletteKey);
            let legacyColors = [];
            if (legacyRaw !== null) {
                try {
                    legacyColors = normalizeColors(JSON.parse(legacyRaw));
                } catch (error) {
                    legacyColors = [];
                }
            }
            ['ink', 'text'].forEach(function (target) {
                const saved = readColorList(paletteKeys[target]);
                state.customColors[target] = saved === null ? legacyColors.slice() : saved;
                if (legacyRaw !== null && saved === null) {
                    window.localStorage.setItem(
                        paletteKeys[target],
                        JSON.stringify(state.customColors[target]),
                    );
                }
            });
            if (legacyRaw !== null) {
                window.localStorage.removeItem(legacyPaletteKey);
            }
        } catch (error) {
            state.customColors = { ink: [], text: [] };
        }
    }

    function setSwatchColor(button, color) {
        if (!button || !validColor(color)) {
            return;
        }
        button.style.backgroundColor = color;
        button.dataset.validColor = color;
    }

    function selectedInkColor() {
        return preferences.color === 'auto' ? resolvedInkColor() : preferences.color;
    }

    function renderCustomColors() {
        toolbar.querySelectorAll('[data-custom-palette]').forEach(function (container) {
            const target = container.dataset.customPalette;
            container.replaceChildren();
            for (let index = 0; index < CUSTOM_SLOTS; index += 1) {
                const color = state.customColors[target][index];
                const button = document.createElement('button');
                button.type = 'button';
                button.className = 'notes-color-swatch notes-custom-color-swatch';
                button.dataset.paletteTarget = target;
                if (color) {
                    button.dataset.paletteColor = color;
                    button.setAttribute('aria-label', color);
                    button.title = color;
                    setSwatchColor(button, color);
                    if (target === 'ink') {
                        button.dataset.inkColor = color;
                    } else {
                        button.dataset.color = color;
                    }
                    const selected = color === (target === 'ink'
                        ? preferences.color
                        : preferences.textColor);
                    button.classList.toggle('is-active', selected);
                    button.setAttribute('aria-pressed', String(selected));
                } else {
                    button.classList.add('is-empty');
                    button.setAttribute('aria-label', 'Cor personalizada vazia');
                    button.title = 'Espaço de cor personalizada vazio';
                    button.setAttribute('aria-pressed', 'false');
                }
                container.append(button);
            }
        });
    }

    function renderPalettes() {
        toolbar.querySelectorAll('[data-ink-color]').forEach(function (button) {
            const color = button.dataset.inkColor;
            if (color === 'auto') {
                setSwatchColor(button, resolvedInkColor());
            } else if (validColor(color)) {
                setSwatchColor(button, color);
            }
            const selected = color === preferences.color;
            button.classList.toggle('is-active', selected);
            button.setAttribute('aria-pressed', String(selected));
        });
        toolbar.querySelectorAll('[data-color]').forEach(function (button) {
            const color = button.dataset.color;
            if (validColor(color)) {
                setSwatchColor(button, color);
            }
            const selected = color === preferences.textColor;
            button.classList.toggle('is-active', selected);
            button.setAttribute('aria-pressed', String(selected));
        });
        const currentInk = toolbar.querySelector('[data-palette-open="ink"]');
        setSwatchColor(currentInk, selectedInkColor());
        currentInk.setAttribute('aria-label', 'Cor atual do lápis: ' + selectedInkColor());
        const currentText = toolbar.querySelector('[data-current-text-color]');
        setSwatchColor(currentText, preferences.textColor);
        renderCustomColors();
    }

    function renderSizeControls() {
        const erasing = state.tool === 'eraser';
        const size = erasing ? preferences.eraserSize : preferences.width;
        widthInput.min = erasing ? '4' : '1';
        widthInput.max = erasing ? '80' : '40';
        widthInput.setAttribute('aria-label', erasing ? 'Diâmetro da borracha' : 'Espessura do lápis');
        widthInput.value = String(size);
        widthValue.textContent = size + ' px';
        widthLabel.textContent = (erasing ? 'Borracha: ' : 'Lápis: ') + size + ' px';
        sizeTrigger.setAttribute('aria-label', 'Tamanho ' + (erasing ? 'da borracha' : 'do lápis') + ': ' + size + ' px');
        widthPreview.style.setProperty('--notes-ink-preview-size', Math.min(size, 80) + 'px');
        widthPreview.classList.toggle('is-eraser-preview', erasing);
        toolbar.querySelectorAll('[data-ink-width]').forEach(function (button) {
            button.hidden = erasing;
            const active = Number(button.dataset.inkWidth) === preferences.width;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
        toolbar.querySelectorAll('[data-eraser-size]').forEach(function (button) {
            button.hidden = !erasing;
            const active = Number(button.dataset.eraserSize) === preferences.eraserSize;
            button.classList.toggle('is-active', active);
            button.setAttribute('aria-pressed', String(active));
        });
    }

    function positionSizePopover() {
        if (sizePopover.hidden) {
            return;
        }
        const triggerRect = sizeTrigger.getBoundingClientRect();
        const popoverRect = sizePopover.getBoundingClientRect();
        const left = Math.max(
            8,
            Math.min(triggerRect.left, window.innerWidth - popoverRect.width - 8),
        );
        const below = triggerRect.bottom + 6;
        const top = below + popoverRect.height <= window.innerHeight - 8
            ? below
            : Math.max(8, triggerRect.top - popoverRect.height - 6);
        sizePopover.style.left = left + 'px';
        sizePopover.style.top = top + 'px';
    }

    function updateSizeFromPopover(event) {
        const widthButton = event.target.closest('[data-ink-width]');
        if (widthButton && !widthButton.hidden) {
            const width = Number(widthButton.dataset.inkWidth);
            if (Number.isInteger(width) && width >= 1 && width <= 40) {
                preferences.width = width;
                renderSizeControls();
                savePreferences();
            }
            return;
        }
        const eraserButton = event.target.closest('[data-eraser-size]');
        if (eraserButton && !eraserButton.hidden) {
            const size = Number(eraserButton.dataset.eraserSize);
            if (Number.isInteger(size) && size >= 4 && size <= 80) {
                preferences.eraserSize = size;
                renderSizeControls();
                setCursorSize();
                savePreferences();
            }
        }
    }

    function getStrokes(elements) {
        return (elements || editor.getElements()).filter(function (element) {
            return element.type === 'stroke' && utils.validStroke(element);
        });
    }

    function getFills(elements) {
        return (elements || editor.getElements()).filter(function (element) {
            return element.type === 'fill' &&
                Number.isInteger(element.x) && Number.isInteger(element.y) &&
                Number.isInteger(element.w) && Number.isInteger(element.h) &&
                typeof element.image === 'string';
        });
    }

    function documentBytes(elements) {
        return new TextEncoder().encode(JSON.stringify({ schema: 1, elements: elements })).length;
    }

    function canCommitStroke(stroke) {
        const elements = editor.getElements();
        const strokes = getStrokes(elements);
        const totalPoints = strokes.reduce(function (total, item) {
            return total + item.points.length / 2;
        }, 0);
        if (strokes.length + 1 > 5000) {
            showMessage('Este conteúdo atingiu o limite de 5.000 traços.');
            return false;
        }
        if (totalPoints + stroke.points.length / 2 > 120_000) {
            showMessage('Este conteúdo atingiu o limite de pontos de desenho.');
            return false;
        }
        if (documentBytes(elements.concat([stroke])) > 1_800_000) {
            showMessage('Este conteúdo está próximo do limite permitido.');
            return false;
        }
        return true;
    }

    function ensureWorldLayers() {
        if (svg.parentElement !== world) {
            world.prepend(svg);
        }
        if (eraserCursor.parentElement !== world) {
            world.append(eraserCursor);
        }
        if (selectionBox.parentElement !== world) {
            world.append(selectionBox);
        }
        const width = Math.max(3000, Number.parseFloat(world.style.width) || 0);
        const height = Math.max(2000, Number.parseFloat(world.style.height) || 0);
        svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
    }

    function pathForStroke(stroke) {
        if (!utils.validStroke(stroke)) {
            return null;
        }
        const pathData = utils.pathData(stroke.points);
        if (!pathData) {
            return null;
        }
        const path = document.createElementNS(svgNamespace, 'path');
        path.dataset.strokeId = stroke.id;
        path.setAttribute('d', pathData);
        path.setAttribute('stroke', stroke.color === 'auto' ? resolvedInkColor() : stroke.color);
        path.setAttribute('stroke-width', String(stroke.width));
        path.setAttribute('stroke-linecap', 'round');
        path.setAttribute('stroke-linejoin', 'round');
        path.classList.toggle('is-selected', state.selectedIds.has(stroke.id));
        path.classList.toggle('is-marquee-selected', state.marqueeIds.has(stroke.id));
        return path;
    }

    function imageForFill(fill) {
        const image = document.createElementNS(svgNamespace, 'image');
        image.dataset.fillId = fill.id;
        image.setAttribute('x', String(fill.x));
        image.setAttribute('y', String(fill.y));
        image.setAttribute('width', String(fill.w));
        image.setAttribute('height', String(fill.h));
        image.setAttribute('preserveAspectRatio', 'none');
        image.setAttribute('href', fill.image);
        image.classList.toggle('is-selected', state.selectedIds.has(fill.id));
        image.classList.toggle('is-marquee-selected', state.marqueeIds.has(fill.id));
        return image;
    }

    function render() {
        ensureWorldLayers();
        rebuildItemBounds();
        const fragment = document.createDocumentFragment();
        state.pathsById.clear();
        const elements = getStrokes().concat(getFills()).map(function (element, index) {
            return { element: element, index: index };
        });
        elements.sort(function (left, right) {
            return left.element.z - right.element.z || left.index - right.index;
        });
        elements.forEach(function (entry) {
            const element = entry.element;
            const drawable = element.type === 'stroke' ? pathForStroke(element) : imageForFill(element);
            if (drawable) {
                state.pathsById.set(element.id, drawable);
                fragment.append(drawable);
            }
        });
        svg.replaceChildren(fragment);
        renderSelectionBounds();
    }

    function worldPoint(event) {
        const rect = world.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const y = event.clientY - rect.top;
        if (!Number.isFinite(x) || !Number.isFinite(y) || x < 0 || y < 0 ||
            x > 20_000 || y > 20_000) {
            return null;
        }
        return { x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10 };
    }

    function appendPoint(points, point) {
        if (!point) {
            return true;
        }
        if (points.length >= 2) {
            const dx = point.x - points[points.length - 2];
            const dy = point.y - points[points.length - 1];
            if (Math.hypot(dx, dy) < 1.5) {
                return true;
            }
        }
        if (points.length >= 10_000) {
            showMessage('Um traço não pode ultrapassar 5.000 pontos.');
            return false;
        }
        points.push(point.x, point.y);
        return true;
    }

    function collectPointerPoints(event, points) {
        const coalesced = typeof event.getCoalescedEvents === 'function'
            ? event.getCoalescedEvents()
            : [];
        const samples = coalesced.length ? coalesced : [event];
        for (const sample of samples) {
            if (!appendPoint(points, worldPoint(sample))) {
                return false;
            }
        }
        if (samples[samples.length - 1] !== event && !appendPoint(points, worldPoint(event))) {
            return false;
        }
        return true;
    }

    function renderLivePath() {
        state.animationFrame = null;
        const active = state.active;
        if (!active) {
            return;
        }
        if (active.kind === 'pencil' && active.path) {
            active.path.setAttribute('d', utils.pathData(active.points));
        } else if (active.kind === 'shape' && active.path) {
            active.points = shapePoints(state.selectedShape, active.start, active.current);
            active.path.setAttribute('d', utils.pathData(active.points));
        } else if (active.kind === 'eraser' && active.pendingElements) {
            editor.updateMutation(active.pendingElements, retainedSelection(active.pendingElements));
        } else if (active.kind === 'marquee') {
            if (active.moved) {
                drawSelectionBox(active.start, active.current);
                const hovered = itemsInsideBox(active.start, active.current);
                const preview = active.additive
                    ? Array.from(new Set(editor.getSelection().concat(hovered)))
                    : hovered;
                updateMarqueePreview(preview);
            }
        } else if (active.kind === 'move' && active.pendingElements) {
            editor.updateMutation(active.pendingElements, active.selectedIds);
        }
    }

    function scheduleRender() {
        if (state.animationFrame === null) {
            state.animationFrame = window.requestAnimationFrame(renderLivePath);
        }
    }

    function setCursorSize() {
        const diameter = preferences.eraserSize;
        eraserCursor.style.width = diameter + 'px';
        eraserCursor.style.height = diameter + 'px';
    }

    function updateEraserCursor(event) {
        const point = worldPoint(event);
        if (!point || state.tool !== 'eraser') {
            eraserCursor.hidden = true;
            return;
        }
        setCursorSize();
        eraserCursor.hidden = false;
        eraserCursor.style.left = point.x + 'px';
        eraserCursor.style.top = point.y + 'px';
    }

    function totalPagePoints(elements) {
        return getStrokes(elements).reduce(function (total, stroke) {
            return total + stroke.points.length / 2;
        }, 0);
    }

    function retainedSelection(elements) {
        const elementIds = new Set(elements.map(function (element) { return element.id; }));
        return editor.getSelection().filter(function (id) { return elementIds.has(id); });
    }

    function candidateWithinLimits(elements) {
        return editor.canUseElements(elements) &&
            getStrokes(elements).length <= 5000 &&
            totalPagePoints(elements) <= 120_000 &&
            documentBytes(elements) <= 1_800_000;
    }

    function boxesIntersect(first, second) {
        return first.minX <= second.maxX && first.maxX >= second.minX &&
            first.minY <= second.maxY && first.maxY >= second.minY;
    }

    function eraseSweep(start, end) {
        const active = state.active;
        if (!active || active.kind !== 'eraser') {
            return;
        }
        const sweepBounds = {
            minX: Math.min(start.x, end.x) - preferences.eraserSize / 2,
            maxX: Math.max(start.x, end.x) + preferences.eraserSize / 2,
            minY: Math.min(start.y, end.y) - preferences.eraserSize / 2,
            maxY: Math.max(start.y, end.y) + preferences.eraserSize / 2,
        };
        const current = active.pendingElements || editor.getElements();
        let changed = false;
        const next = [];
        current.forEach(function (element) {
            if (element.type !== 'stroke') {
                next.push(element);
                return;
            }
            const box = utils.bounds(element.points);
            const radius = preferences.eraserSize / 2 + element.width / 2;
            const expanded = {
                minX: box.minX - radius,
                minY: box.minY - radius,
                maxX: box.maxX + radius,
                maxY: box.maxY + radius,
            };
            if (!boxesIntersect(sweepBounds, expanded)) {
                next.push(element);
                return;
            }
            const pieces = utils.cutPolyline(element.points, start, end, radius);
            const unchanged = pieces.length === 1 && pieces[0].length === element.points.length &&
                pieces[0].every(function (coordinate, index) {
                    return coordinate === element.points[index];
                });
            if (unchanged) {
                next.push(element);
                return;
            }
            const fragments = pieces.map(function (points) {
                return {
                    id: window.crypto.randomUUID(),
                    type: 'stroke',
                    points: points,
                    color: element.color,
                    width: element.width,
                    z: element.z,
                };
            });
            const candidate = next.concat(fragments, current.slice(current.indexOf(element) + 1));
            if (!candidateWithinLimits(candidate)) {
                showMessage('O corte excederia o limite de desenho deste conteúdo.');
                next.push(element);
                return;
            }
            next.push.apply(next, fragments);
            active.changed = true;
            changed = true;
        });
        if (changed) {
            active.pendingElements = next;
            scheduleRender();
        }
    }

    function drawSelectionBox(start, end) {
        const left = Math.min(start.x, end.x);
        const top = Math.min(start.y, end.y);
        selectionBox.hidden = false;
        selectionBox.style.left = left + 'px';
        selectionBox.style.top = top + 'px';
        selectionBox.style.width = Math.abs(end.x - start.x) + 'px';
        selectionBox.style.height = Math.abs(end.y - start.y) + 'px';
    }

    function measureItemBounds(element) {
        if (element.type === 'stroke') {
            return utils.bounds(element.points);
        }
        if (element.type === 'fill') {
            return {
                minX: element.x,
                minY: element.y,
                maxX: element.x + element.w,
                maxY: element.y + element.h,
            };
        }
        const block = world.querySelector('[data-block-id="' + element.id + '"]');
        const rect = block ? block.getBoundingClientRect() : null;
        const worldRect = world.getBoundingClientRect();
        return rect
            ? {
                minX: rect.left - worldRect.left,
                minY: rect.top - worldRect.top,
                maxX: rect.right - worldRect.left,
                maxY: rect.bottom - worldRect.top,
            }
            : {
                minX: element.x,
                minY: element.y,
                maxX: element.x + element.w,
                maxY: element.y + 40,
            };
    }

    function itemBounds(element) {
        const cached = state.itemBounds.get(element.id);
        if (!cached || cached.element !== element) {
            const bounds = measureItemBounds(element);
            state.itemBounds.set(element.id, { element: element, bounds: bounds });
            return bounds;
        }
        return cached.bounds;
    }

    function refreshItemBounds(id) {
        const element = elementForId(id);
        if (element) {
            state.itemBounds.set(id, {
                element: element,
                bounds: measureItemBounds(element),
            });
        } else {
            state.itemBounds.delete(id);
        }
    }

    function rebuildItemBounds() {
        const elements = editor.getElements();
        const ids = new Set(elements.map(function (element) { return element.id; }));
        state.itemBounds.forEach(function (cached, id) {
            if (!ids.has(id)) {
                state.itemBounds.delete(id);
            }
        });
        elements.forEach(function (element) {
            itemBounds(element);
        });
    }

    function itemsInsideBox(start, end) {
        const box = {
            minX: Math.min(start.x, end.x),
            maxX: Math.max(start.x, end.x),
            minY: Math.min(start.y, end.y),
            maxY: Math.max(start.y, end.y),
        };
        return editor.getElements().filter(function (element) {
            const item = itemBounds(element);
            if (!item) {
                return false;
            }
            if (element.type === 'stroke') {
                const halfWidth = element.width / 2;
                const expanded = {
                    minX: item.minX - halfWidth,
                    minY: item.minY - halfWidth,
                    maxX: item.maxX + halfWidth,
                    maxY: item.maxY + halfWidth,
                };
                if (!boxesIntersect(expanded, box)) {
                    return false;
                }
                const hitBox = {
                    minX: box.minX - halfWidth,
                    minY: box.minY - halfWidth,
                    maxX: box.maxX + halfWidth,
                    maxY: box.maxY + halfWidth,
                };
                for (let index = 0; index < element.points.length - 2; index += 2) {
                    if (segmentIntersectsBox(
                        element.points[index],
                        element.points[index + 1],
                        element.points[index + 2],
                        element.points[index + 3],
                        hitBox,
                    )) {
                        return true;
                    }
                }
                return segmentIntersectsBox(
                    element.points[0],
                    element.points[1],
                    element.points[0],
                    element.points[1],
                    hitBox,
                );
            }
            return boxesIntersect(item, box);
        }).map(function (element) { return element.id; });
    }

    function segmentIntersectsBox(x0, y0, x1, y1, box) {
        const dx = x1 - x0;
        const dy = y1 - y0;
        const p = [-dx, dx, -dy, dy];
        const q = [x0 - box.minX, box.maxX - x0, y0 - box.minY, box.maxY - y0];
        let min = 0;
        let max = 1;
        for (let index = 0; index < 4; index += 1) {
            if (p[index] === 0) {
                if (q[index] < 0) {
                    return false;
                }
                continue;
            }
            const ratio = q[index] / p[index];
            if (p[index] < 0) {
                min = Math.max(min, ratio);
            } else {
                max = Math.min(max, ratio);
            }
            if (min > max) {
                return false;
            }
        }
        return true;
    }

    function hitDrawable(point) {
        return editor.getElements().filter(function (element) {
            return element.type === 'stroke' || element.type === 'fill';
        }).slice().sort(function (left, right) {
            return right.z - left.z;
        }).find(function (element) {
            if (element.type === 'fill') {
                return point.x >= element.x && point.x <= element.x + element.w &&
                    point.y >= element.y && point.y <= element.y + element.h;
            }
            return utils.hitTestStroke(element, point.x, point.y, Math.max(4, 6 - element.width / 2));
        }) || null;
    }

    function fillAtPoint(point) {
        const worldWidth = Math.max(1, Math.min(20_000, Number.parseFloat(world.style.width) || 3000));
        const worldHeight = Math.max(1, Math.min(20_000, Number.parseFloat(world.style.height) || 2000));
        const scale = Math.min(1, Math.sqrt(6_000_000 / (worldWidth * worldHeight)));
        const width = Math.max(1, Math.floor(worldWidth * scale));
        const height = Math.max(1, Math.floor(worldHeight * scale));
        const canvas = document.createElement('canvas');
        canvas.width = width;
        canvas.height = height;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) {
            showMessage('Não foi possível preparar a área para preenchimento.');
            return;
        }
        context.fillStyle = '#ffffff';
        context.fillRect(0, 0, width, height);
        context.strokeStyle = '#000000';
        context.fillStyle = '#000000';
        context.lineCap = 'round';
        context.lineJoin = 'round';
        getStrokes().forEach(function (stroke) {
            context.lineWidth = Math.max(1, stroke.width * scale + 1);
            context.beginPath();
            if (stroke.points.length === 2) {
                context.arc(
                    stroke.points[0] * scale,
                    stroke.points[1] * scale,
                    context.lineWidth / 2,
                    0,
                    Math.PI * 2,
                );
                context.fill();
                return;
            }
            context.moveTo(stroke.points[0] * scale, stroke.points[1] * scale);
            for (let index = 2; index < stroke.points.length; index += 2) {
                context.lineTo(stroke.points[index] * scale, stroke.points[index + 1] * scale);
            }
            context.stroke();
        });

        const seedX = Math.floor(point.x * scale);
        const seedY = Math.floor(point.y * scale);
        if (seedX < 0 || seedY < 0 || seedX >= width || seedY >= height) {
            return;
        }
        const barrierPixels = context.getImageData(0, 0, width, height).data;
        const pixelCount = width * height;
        const visited = new Uint8Array(pixelCount);
        for (let index = 0; index < pixelCount; index += 1) {
            if (barrierPixels[index * 4] < 245) {
                visited[index] = 1;
            }
        }
        const seed = seedY * width + seedX;
        if (visited[seed]) {
            showMessage('Clique dentro de uma área para preenchê-la.');
            return;
        }
        const queue = new Int32Array(pixelCount);
        let head = 0;
        let tail = 1;
        queue[0] = seed;
        visited[seed] = 2;
        let minX = seedX;
        let maxX = seedX;
        let minY = seedY;
        let maxY = seedY;
        while (head < tail) {
            const index = queue[head];
            head += 1;
            const x = index % width;
            const y = Math.floor(index / width);
            minX = Math.min(minX, x);
            maxX = Math.max(maxX, x);
            minY = Math.min(minY, y);
            maxY = Math.max(maxY, y);
            let neighbor = x > 0 ? index - 1 : -1;
            if (neighbor >= 0 && visited[neighbor] === 0) {
                visited[neighbor] = 2;
                queue[tail] = neighbor;
                tail += 1;
            }
            neighbor = x + 1 < width ? index + 1 : -1;
            if (neighbor >= 0 && visited[neighbor] === 0) {
                visited[neighbor] = 2;
                queue[tail] = neighbor;
                tail += 1;
            }
            neighbor = y > 0 ? index - width : -1;
            if (neighbor >= 0 && visited[neighbor] === 0) {
                visited[neighbor] = 2;
                queue[tail] = neighbor;
                tail += 1;
            }
            neighbor = y + 1 < height ? index + width : -1;
            if (neighbor >= 0 && visited[neighbor] === 0) {
                visited[neighbor] = 2;
                queue[tail] = neighbor;
                tail += 1;
            }
        }

        const imageX = Math.floor(minX / scale);
        const imageY = Math.floor(minY / scale);
        const imageRight = Math.ceil((maxX + 1) / scale);
        const imageBottom = Math.ceil((maxY + 1) / scale);
        const imageWidth = imageRight - imageX;
        const imageHeight = imageBottom - imageY;
        if (imageWidth * imageHeight > 6_000_000 ||
            imageX + imageWidth > 20_000 || imageY + imageHeight > 20_000) {
            showMessage('A área é grande demais para ser preenchida de uma só vez.');
            return;
        }
        const color = selectedInkColor();
        const red = parseInt(color.slice(1, 3), 16);
        const green = parseInt(color.slice(3, 5), 16);
        const blue = parseInt(color.slice(5, 7), 16);
        const fillCanvas = document.createElement('canvas');
        fillCanvas.width = imageWidth;
        fillCanvas.height = imageHeight;
        const fillContext = fillCanvas.getContext('2d');
        if (!fillContext) {
            showMessage('Não foi possível criar a imagem de preenchimento.');
            return;
        }
        const fillImage = fillContext.createImageData(imageWidth, imageHeight);
        for (let y = 0; y < imageHeight; y += 1) {
            const sourceY = Math.min(height - 1, Math.floor((imageY + y) * scale));
            for (let x = 0; x < imageWidth; x += 1) {
                const sourceX = Math.min(width - 1, Math.floor((imageX + x) * scale));
                if (visited[sourceY * width + sourceX] !== 2) {
                    continue;
                }
                const offset = (y * imageWidth + x) * 4;
                fillImage.data[offset] = red;
                fillImage.data[offset + 1] = green;
                fillImage.data[offset + 2] = blue;
                fillImage.data[offset + 3] = 255;
            }
        }
        fillContext.putImageData(fillImage, 0, 0);
        const image = fillCanvas.toDataURL('image/png');
        if (image.length > 1_000_000) {
            showMessage('A imagem de preenchimento excede o limite permitido.');
            return;
        }
        const fill = {
            id: window.crypto.randomUUID(),
            type: 'fill',
            x: imageX,
            y: imageY,
            w: imageWidth,
            h: imageHeight,
            z: Math.min(100_000, Math.max.apply(null, editor.getElements().map(function (element) {
                return element.z;
            }).concat([0])) + 1),
            image: image,
            color: color,
        };
        if (!editor.addFill(fill)) {
            showMessage('Este preenchimento excederia o limite permitido para a página.');
            return;
        }
        state.nextStrokeZ = Math.max(state.nextStrokeZ, fill.z + 1);
        clearMessage();
    }

    function updateMarqueePreview(ids) {
        state.marqueeIds = new Set(ids);
        state.pathsById.forEach(function (path, id) {
            path.classList.toggle(
                'is-marquee-selected',
                state.marqueeIds.has(id) && !state.selectedIds.has(id),
            );
        });
        world.querySelectorAll('.notes-text-block').forEach(function (block) {
            block.classList.toggle(
                'is-marquee-selected',
                state.marqueeIds.has(block.dataset.blockId) &&
                    !state.selectedIds.has(block.dataset.blockId),
            );
        });
    }

    function elementForId(id) {
        return editor.getElements().find(function (element) { return element.id === id; }) || null;
    }

    function moveCandidate(snapshot, ids, dx, dy) {
        const selected = snapshot.filter(function (element) { return ids.includes(element.id); });
        const boxes = selected.map(itemBounds).filter(Boolean);
        if (!boxes.length) {
            return snapshot;
        }
        const bounds = boxes.reduce(function (combined, box) {
            return {
                minX: Math.min(combined.minX, box.minX),
                minY: Math.min(combined.minY, box.minY),
                maxX: Math.max(combined.maxX, box.maxX),
                maxY: Math.max(combined.maxY, box.maxY),
            };
        }, { minX: 20_000, minY: 20_000, maxX: 0, maxY: 0 });
        const offsetX = Math.max(-bounds.minX, Math.min(20_000 - bounds.maxX, dx));
        const offsetY = Math.max(-bounds.minY, Math.min(20_000 - bounds.maxY, dy));
        return snapshot.map(function (element) {
            if (!ids.includes(element.id)) {
                return element;
            }
            const copy = JSON.parse(JSON.stringify(element));
            if (copy.type === 'stroke') {
                for (let index = 0; index < copy.points.length; index += 2) {
                    copy.points[index] = Math.round((copy.points[index] + offsetX) * 10) / 10;
                    copy.points[index + 1] = Math.round((copy.points[index + 1] + offsetY) * 10) / 10;
                }
            } else {
                copy.x = Math.round(copy.x + offsetX);
                copy.y = Math.round(copy.y + offsetY);
            }
            return copy;
        });
    }

    function beginInteraction(event) {
        if (state.activePointerId !== null) {
            return;
        }
        if (event.button !== undefined && event.button !== 0) {
            return;
        }
        const point = worldPoint(event);
        if (!point || !editor.getPageId()) {
            return;
        }
        if (state.tool === 'bucket') {
            event.preventDefault();
            editor.finishTextEditing();
            fillAtPoint(point);
            return;
        }
        if (state.tool === 'shape') {
            event.preventDefault();
            editor.finishTextEditing();
            const path = document.createElementNS(svgNamespace, 'path');
            path.setAttribute('stroke', selectedInkColor());
            path.setAttribute('stroke-width', String(preferences.width));
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('fill', 'none');
            path.setAttribute('d', utils.pathData(shapePoints(state.selectedShape, point, point)));
            svg.append(path);
            state.active = {
                kind: 'shape',
                path: path,
                start: point,
                current: point,
                points: shapePoints(state.selectedShape, point, point),
                overflow: false,
            };
            state.activePointerId = event.pointerId;
            workArea.setPointerCapture(event.pointerId);
            return;
        }
        if (state.tool === 'pencil') {
            event.preventDefault();
            editor.finishTextEditing();
            state.activePointerId = event.pointerId;
            workArea.setPointerCapture(event.pointerId);
            const path = document.createElementNS(svgNamespace, 'path');
            const points = [];
            appendPoint(points, point);
            path.setAttribute('stroke', selectedInkColor());
            path.setAttribute('stroke-width', String(preferences.width));
            path.setAttribute('stroke-linecap', 'round');
            path.setAttribute('stroke-linejoin', 'round');
            path.setAttribute('fill', 'none');
            path.setAttribute('d', utils.pathData(points));
            svg.append(path);
            state.active = { kind: 'pencil', path: path, points: points, overflow: false };
            return;
        }
        if (state.tool === 'eraser') {
            event.preventDefault();
            editor.finishTextEditing();
            state.activePointerId = event.pointerId;
            workArea.setPointerCapture(event.pointerId);
            state.active = {
                kind: 'eraser',
                snapshot: editor.beginMutation(),
                previous: point,
                pendingElements: null,
                changed: false,
            };
            eraseSweep(point, point);
            updateEraserCursor(event);
            return;
        }
        if (state.tool !== 'select' || event.target.closest('.notes-block-handle, .notes-block-resize')) {
            return;
        }
        const textContent = event.target.closest('.notes-text-content');
        if (textContent && textContent.isContentEditable) {
            return;
        }
        editor.finishTextEditing();

        let selectedElement = null;
        const block = event.target.closest('.notes-text-block');
        if (block) {
            selectedElement = elementForId(block.dataset.blockId);
            if (textContent && !editor.getSelection().includes(block.dataset.blockId)) {
                return;
            }
        } else {
            selectedElement = hitStroke(point);
        }
        if (selectedElement) {
            const modifier = event.shiftKey || event.ctrlKey || event.metaKey;
            const alreadySelected = editor.getSelection().includes(selectedElement.id);
            if (alreadySelected && !modifier && pointInsideSelection(point)) {
                state.active = {
                    kind: 'move',
                    pointerId: event.pointerId,
                    start: point,
                    selectedIds: editor.getSelection(),
                    snapshot: null,
                    pendingElements: null,
                    changed: false,
                };
                event.preventDefault();
                state.activePointerId = event.pointerId;
                workArea.setPointerCapture(event.pointerId);
                return;
            }
            editor.setSelection([selectedElement.id], modifier ? 'toggle' : 'replace');
            if (modifier && alreadySelected) {
                return;
            }
            state.active = {
                kind: 'item',
                pointerId: event.pointerId,
                start: point,
                last: point,
                moved: false,
            };
        } else if (editor.getSelectionBounds() && pointInsideSelection(point)) {
            state.active = {
                kind: 'move',
                pointerId: event.pointerId,
                start: point,
                selectedIds: editor.getSelection(),
                snapshot: null,
                pendingElements: null,
                changed: false,
            };
        } else {
            state.active = {
                kind: 'marquee',
                pointerId: event.pointerId,
                start: point,
                current: point,
                moved: false,
                additive: event.shiftKey || event.ctrlKey || event.metaKey,
            };
            selectionBox.hidden = true;
        }
        event.preventDefault();
        state.activePointerId = event.pointerId;
        workArea.setPointerCapture(event.pointerId);
    }

    function pointInsideSelection(point) {
        const bounds = editor.getSelectionBounds();
        return Boolean(bounds && point.x >= bounds.minX && point.x <= bounds.maxX &&
            point.y >= bounds.minY && point.y <= bounds.maxY);
    }

    function updateInteraction(event) {
        updateEraserCursor(event);
        if (state.activePointerId === null || event.pointerId !== state.activePointerId || !state.active) {
            return;
        }
        const point = worldPoint(event);
        if (!point) {
            return;
        }
        const active = state.active;
        if (active.kind === 'pencil') {
            if (!collectPointerPoints(event, active.points)) {
                active.overflow = true;
            } else if (totalPagePoints() + active.points.length / 2 > 120_000) {
                active.overflow = true;
                showMessage('Este conteúdo atingiu o limite de pontos de desenho.');
            }
            scheduleRender();
        } else if (active.kind === 'shape') {
            active.current = point;
            scheduleRender();
        } else if (active.kind === 'eraser') {
            eraseSweep(active.previous, point);
            active.previous = point;
            updateEraserCursor(event);
        } else if (active.kind === 'marquee') {
            active.current = point;
            if (!active.moved && Math.hypot(point.x - active.start.x, point.y - active.start.y) >= 3) {
                active.moved = true;
            }
            if (active.moved) {
                scheduleRender();
            }
        } else if (active.kind === 'item') {
            if (!active.moved && Math.hypot(point.x - active.start.x, point.y - active.start.y) >= 3) {
                active.moved = true;
                active.selectedIds = editor.getSelection();
                active.snapshot = editor.beginMutation();
            }
            if (active.moved) {
                active.pendingElements = moveCandidate(
                    active.snapshot,
                    active.selectedIds,
                    point.x - active.start.x,
                    point.y - active.start.y,
                );
                active.last = point;
                active.changed = true;
                scheduleRender();
            }
        } else if (active.kind === 'move') {
            if (!active.snapshot && Math.hypot(point.x - active.start.x, point.y - active.start.y) >= 3) {
                active.snapshot = editor.beginMutation();
            }
            if (active.snapshot) {
                active.pendingElements = moveCandidate(
                    active.snapshot,
                    active.selectedIds,
                    point.x - active.start.x,
                    point.y - active.start.y,
                );
                active.changed = true;
                scheduleRender();
            }
        }
    }

    function finishInteraction(event, cancelled) {
        if (state.activePointerId === null || event.pointerId !== state.activePointerId) {
            return;
        }
        const active = state.active;
        if (state.animationFrame !== null) {
            window.cancelAnimationFrame(state.animationFrame);
            state.animationFrame = null;
        }
        if (active && active.kind === 'pencil') {
            if (!cancelled) {
                collectPointerPoints(event, active.points);
            }
            if (cancelled || active.overflow) {
                active.path.remove();
            } else {
                const stroke = {
                    id: window.crypto.randomUUID(),
                    type: 'stroke',
                    points: utils.simplify(active.points, 0.8).map(function (coordinate) {
                        return Math.round(coordinate * 10) / 10;
                    }),
                    color: preferences.color,
                    width: preferences.width,
                    z: state.nextStrokeZ,
                };
                if (utils.validStroke(stroke) && canCommitStroke(stroke)) {
                    state.nextStrokeZ = Math.min(100_000, state.nextStrokeZ + 1);
                    editor.addStroke(stroke);
                    clearMessage();
                } else {
                    active.path.remove();
                }
            }
        } else if (active && active.kind === 'shape') {
            if (!cancelled) {
                active.current = worldPoint(event) || active.current;
                active.points = shapePoints(state.selectedShape, active.start, active.current);
                const stroke = {
                    id: window.crypto.randomUUID(),
                    type: 'stroke',
                    points: active.points.map(function (coordinate) {
                        return Math.round(coordinate * 10) / 10;
                    }),
                    color: preferences.color,
                    width: preferences.width,
                    z: state.nextStrokeZ,
                };
                if (utils.validStroke(stroke) && canCommitStroke(stroke)) {
                    state.nextStrokeZ = Math.min(100_000, state.nextStrokeZ + 1);
                    editor.addStroke(stroke);
                } else {
                    active.path.remove();
                }
            } else {
                active.path.remove();
            }
        } else if (active && active.kind === 'eraser') {
            if (cancelled) {
                editor.cancelMutation(active.snapshot);
            } else if (active.changed && active.pendingElements) {
                editor.updateMutation(active.pendingElements, retainedSelection(active.pendingElements));
                editor.commitMutation();
                clearMessage();
            } else {
                editor.cancelMutation(active.snapshot);
            }
        } else if (active && active.kind === 'marquee') {
            selectionBox.hidden = true;
            if (active.moved) {
                const selected = itemsInsideBox(active.start, active.current);
                const preview = active.additive
                    ? Array.from(new Set(editor.getSelection().concat(selected)))
                    : selected;
                updateMarqueePreview(preview);
                editor.setSelection(selected, active.additive ? 'add' : 'replace');
            } else if (active.additive) {
                editor.setSelection([], 'add');
            } else {
                editor.setSelection([]);
            }
            updateMarqueePreview([]);
        } else if (active && (active.kind === 'item' || active.kind === 'move')) {
            selectionBox.hidden = true;
            if (active.snapshot && active.changed && active.pendingElements) {
                editor.updateMutation(active.pendingElements, active.selectedIds);
                editor.commitMutation();
            } else if (active.snapshot) {
                editor.cancelMutation(active.snapshot);
            }
        }
        state.active = null;
        state.activePointerId = null;
        if (workArea.hasPointerCapture(event.pointerId)) {
            workArea.releasePointerCapture(event.pointerId);
        }
    }

    function cancelInteraction() {
        const active = state.active;
        if (!active) {
            return;
        }
        const pointerId = state.activePointerId;
        if (state.animationFrame !== null) {
            window.cancelAnimationFrame(state.animationFrame);
            state.animationFrame = null;
        }
        if (active.kind === 'pencil' || active.kind === 'shape') {
            active.path.remove();
        } else if ((active.kind === 'eraser' || active.kind === 'move' || active.kind === 'item') &&
            active.snapshot) {
            editor.cancelMutation(active.snapshot);
        } else if (active.kind === 'marquee') {
            selectionBox.hidden = true;
            updateMarqueePreview([]);
        }
        state.active = null;
        state.activePointerId = null;
        if (pointerId !== null && workArea.hasPointerCapture(pointerId)) {
            workArea.releasePointerCapture(pointerId);
        }
    }

    function updateTool(tool) {
        if (state.active && tool !== state.active.kind) {
            cancelInteraction();
        }
        state.tool = tool;
        workArea.dataset.tool = tool;
        world.dataset.inkTool = tool === 'pencil' || tool === 'eraser' ||
            tool === 'bucket' || tool === 'shape' ? tool : '';
        eraserCursor.hidden = tool !== 'eraser';
        renderSizeControls();
        if (tool !== 'eraser') {
            clearMessage();
        }
    }

    function saveCustomColor(color, target) {
        state.customColors[target] = [color].concat(state.customColors[target].filter(function (item) {
            return item !== color;
        })).slice(0, CUSTOM_SLOTS);
        try {
            window.localStorage.setItem(
                paletteKeys[target],
                JSON.stringify(state.customColors[target]),
            );
        } catch (error) {
            return;
        } finally {
            renderPalettes();
        }
    }

    function applyInkColor(color) {
        if (color !== 'auto' && !validColor(color)) {
            return;
        }
        preferences.color = color;
        renderPalettes();
        savePreferences();
    }

    function applyTextColor(color) {
        if (!validColor(color)) {
            return;
        }
        preferences.textColor = color;
        renderPalettes();
        savePreferences();
        window.dispatchEvent(new CustomEvent('notes:apply-text-color', { detail: { color: color } }));
    }

    function updateCustomColor(event, save) {
        const color = event.currentTarget.value.toLowerCase();
        if (!validColor(color)) {
            return;
        }
        const target = event.currentTarget === textColorInput ? 'text' : 'ink';
        if (save) {
            saveCustomColor(color, target);
        }
        if (target === 'text') {
            applyTextColor(color);
            return;
        }
        applyInkColor(color);
    }

    function openColorPicker(target) {
        const input = target === 'text' ? textColorInput : colorInput;
        input.value = target === 'text' ? preferences.textColor : selectedInkColor();
        input.click();
    }

    function renderSelectionBounds() {
        const bounds = editor.getSelectionBounds();
        if (!bounds || state.selectedIds.size < 2) {
            selectionBox.hidden = true;
            selectionBox.classList.remove('is-marquee');
            return;
        }
        selectionBox.hidden = false;
        selectionBox.classList.remove('is-marquee');
        selectionBox.style.left = bounds.minX + 'px';
        selectionBox.style.top = bounds.minY + 'px';
        selectionBox.style.width = Math.max(1, bounds.maxX - bounds.minX) + 'px';
        selectionBox.style.height = Math.max(1, bounds.maxY - bounds.minY) + 'px';
    }

    function updateSelection(ids) {
        state.selectedIds = new Set(ids);
        state.pathsById.forEach(function (path, id) {
            path.classList.toggle('is-selected', state.selectedIds.has(id));
            path.classList.toggle('is-marquee-selected', state.marqueeIds.has(id));
        });
        world.querySelectorAll('.notes-text-block').forEach(function (block) {
            block.classList.toggle('is-marquee-selected', state.marqueeIds.has(block.dataset.blockId));
        });
        renderSelectionBounds();
    }

    toolbar.addEventListener('click', function (event) {
        const colorOpen = event.target.closest('[data-palette-open]');
        if (colorOpen) {
            openColorPicker(colorOpen.dataset.paletteOpen);
            return;
        }
        if (event.target.closest('[data-color-picker]')) {
            const palette = event.target.closest('[data-palette]');
            openColorPicker(palette && palette.dataset.palette === 'text' ? 'text' : 'ink');
            return;
        }
        const colorButton = event.target.closest('[data-ink-color]');
        if (colorButton) {
            applyInkColor(colorButton.dataset.inkColor);
            return;
        }
        const textButton = event.target.closest('[data-color]');
        if (textButton && validColor(textButton.dataset.color)) {
            applyTextColor(textButton.dataset.color);
            return;
        }
        if (event.target.closest('[data-size-toggle]')) {
            sizePopover.hidden = !sizePopover.hidden;
            sizeTrigger.setAttribute('aria-expanded', String(!sizePopover.hidden));
            positionSizePopover();
        }
    });
    sizePopover.addEventListener('click', updateSizeFromPopover);

    [colorInput, textColorInput].forEach(function (input) {
        input.addEventListener('input', function (event) {
            updateCustomColor(event, false);
        });
        input.addEventListener('change', function (event) {
            updateCustomColor(event, true);
        });
    });
    widthInput.addEventListener('input', function () {
        const value = Number(widthInput.value);
        if (state.tool === 'eraser') {
            if (Number.isInteger(value) && value >= 4 && value <= 80) {
                preferences.eraserSize = value;
                setCursorSize();
            }
        } else if (Number.isInteger(value) && value >= 1 && value <= 40) {
            preferences.width = value;
        }
        renderSizeControls();
        savePreferences();
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('.notes-size-group, #notesSizePopover')) {
            sizePopover.hidden = true;
            sizeTrigger.setAttribute('aria-expanded', 'false');
        }
    });
    document.addEventListener('scroll', positionSizePopover, true);
    window.addEventListener('resize', positionSizePopover);
    workArea.addEventListener('pointerdown', beginInteraction);
    workArea.addEventListener('pointermove', updateInteraction);
    workArea.addEventListener('pointerup', function (event) { finishInteraction(event, false); });
    workArea.addEventListener('pointercancel', function (event) { finishInteraction(event, true); });
    workArea.addEventListener('lostpointercapture', function (event) {
        if (state.activePointerId === event.pointerId) {
            cancelInteraction();
        }
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && state.active) {
            event.preventDefault();
            cancelInteraction();
        }
    });
    window.addEventListener('resize', renderSelectionBounds);
    window.addEventListener('scroll', renderSelectionBounds, true);
    window.addEventListener('notes:tool-change', function (event) {
        updateTool(event.detail.tool);
    });
    window.addEventListener('notes:page-loaded', function () {
        const drawables = editor.getElements().filter(function (element) {
            return element.type === 'stroke' || element.type === 'fill';
        });
        state.nextStrokeZ = drawables.reduce(function (maximum, element) {
            return Math.max(maximum, element.z + 1);
        }, 1);
        state.selectedIds.clear();
        render();
    });
    window.addEventListener('notes:clear-page', function () {
        cancelInteraction();
        svg.replaceChildren();
        state.pathsById.clear();
        state.selectedIds.clear();
        state.marqueeIds.clear();
        state.itemBounds.clear();
        selectionBox.hidden = true;
        state.nextStrokeZ = 1;
    });

    window.notesInk = {
        render: render,
        updateSelection: updateSelection,
        refreshItemBounds: refreshItemBounds,
        isInteracting: function () { return state.activePointerId !== null; },
        cancelInteraction: cancelInteraction,
    };
    loadPreferences();
    renderPalettes();
    updateTool(state.tool);
    renderSizeControls();
    render();
}());
