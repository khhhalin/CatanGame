// Customize appearance — a client-only restyle of this browser's own view.
//
// Phase A of the UI-customization effort: a player reshapes their own overlay
// without touching the server, the engine, or anyone else's screen. Everything
// here is local — one localStorage key, one pair of injected <style> elements —
// so a customization travels with the browser and a bad Custom CSS rule breaks
// only the tab that wrote it (Reset recovers it).
//
// This is a CLASSIC script, loaded in <head> BEFORE the body renders, on
// purpose: the stored overrides are applied synchronously the moment the file
// runs, so a customized browser paints customized on the first frame with no
// flash of the default look. The panel's own wiring waits for DOMContentLoaded,
// since its controls do not exist yet when the file first runs.
//
// It drives the token system rather than any per-panel CSS: the structured
// controls redefine `:root` tokens (--panel-opacity, --panel-tint, --glass,
// --font-ui, --text-scale, --accent…) that every panel already reads, so one
// lever moves every surface at once. See tokens.css for the levers.

(function () {
    'use strict';

    const STORAGE_KEY = 'catan.customize';
    const OVERRIDE_STYLE_ID = 'user-overrides';
    const CUSTOM_CSS_STYLE_ID = 'user-custom-css';
    const LAYOUT_STYLE_ID = 'user-layout';

    // Phase B: the floating board overlays a player may drag to reposition.
    // Keyed by element id; the value is the panel's default in-game `transform`,
    // which the drag offset composes onto so a centred float stays centred as it
    // moves. Each is position:absolute inside #board-overlays, so an offset is
    // pure geometry — no token work. The docked left-rail asides (bank, log) are
    // grid cells, not floats, so they are deliberately not draggable here.
    const DRAGGABLE = {
        'players-panel': '',            // scoreboard float, top-right in game
        'action-tray': '',              // build & trade tray (holds #game-console)
        'dice-footer': '',              // the dice float, bottom-right
        'settings-float': 'translateX(-50%)', // colour/YOLO/mute chip, top-centre
        'incoming-offers': '',          // incoming trade-offer cards
    };

    // A dragged panel is clamped so at least this much of it stays on screen —
    // dragging can never lose a panel off an edge (Reset layout also recovers).
    const KEEP_ON_SCREEN = 40;

    // Phase C: the readout "widgets" a player may pull out of the rail and
    // compose into their own HUD. Keyed by the id of an EXISTING rail element —
    // no new readout is invented; each is wrapped where it already lives. The
    // value is the label shown in the Widgets checklist.
    //
    // The choice of element matters: every renderer here writes into a child by
    // id (bank.js -> #bank-display inside #right-bank, scoreboard.js ->
    // #award-summary inside #right-titles, panels.js -> #build-costs inside
    // #costs-panel, and so on), never into the container itself, so moving the
    // container leaves the live update path intact — getElementById still finds
    // the child wherever the container is re-parented to. #turn-banner is the one
    // whose renderer rewrites its own innerHTML, which is why the hide affordance
    // is a checklist in the panel and not a tag injected into the widget: an
    // injected child would be wiped on the next board update.
    //
    // The Phase-B floats (scoreboard, dice, tray, settings, offers) are NOT
    // listed here on purpose: they already carry a whole-panel transform drag,
    // and a second drag owner on the same element would fight it.
    const WIDGETS = {
        'turn-banner': 'Turn & round',
        'right-bank': 'Bank',
        'right-titles': 'Titles',
        'costs-panel': 'Costs',
        'dev-cards-panel': 'Dev cards',
        'knights-panel': 'Knights',
        'chat-panel': 'Game log',
    };

    // The fixed overlay layer the HUD composes into: custom panels and any
    // free-positioned widget are absolutely placed inside it, so they track the
    // board box (overlays.js pins it) exactly as the Phase-B floats do.
    const HUD_LAYER_ID = 'board-overlays';

    // The bundled faces (fonts.css) plus a few safe system stacks. The value is
    // dropped straight into --font-ui; the empty value means "leave the theme's
    // own font", which keeps the default byte-identical.
    const FONT_STACKS = {
        space: "'Space Grotesk', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        mono: "'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
        system: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
        serif: "Georgia, 'Times New Roman', Times, serif",
        monospace: "ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
    };

    // An empty config sets nothing: every field is null/blank until a control is
    // touched, so an unconfigured browser injects an empty rule and looks
    // exactly as it does today.
    function emptyConfig() {
        return {
            panelOpacity: null,   // 0..1
            fontKey: null,        // a FONT_STACKS key
            textScale: null,      // e.g. 1.1
            panelBg: null,        // {mode:'solid', color} | {mode:'gradient', angle, c1, c2}
            accent: null,         // '#rrggbb'
            customCss: '',        // raw CSS, injected verbatim
            layout: {},           // Phase B: {panelId: {x, y}} drag offsets, px
            hud: emptyHud(),      // Phase C: the composed HUD (widgets + panels)
        };
    }

    // Phase C composition. `widgets` carries per-widget overrides for widgets
    // NOT placed in a custom panel: {hidden} takes a readout off screen, {x, y}
    // free-positions it in the overlay layer. `panels` is the ordered list of
    // custom panels, each owning the widgets dropped into it. A widget listed in
    // a panel's `widgets` array lives there; its entry in `widgets` (if any) only
    // still governs whether it is hidden. An empty hud injects and re-parents
    // nothing, so an unconfigured browser is byte-identical.
    function emptyHud() {
        return {
            widgets: {},   // {widgetId: {hidden?: bool, x?: num, y?: num}}
            panels: [],    // [{id, x, y, widgets: [widgetId, ...]}]
        };
    }

    function hudIsEmpty(hud) {
        if (!hud) {
            return true;
        }
        const panels = hud.panels || [];
        const widgets = hud.widgets || {};
        return panels.length === 0 && Object.keys(widgets).length === 0;
    }

    function loadConfig() {
        try {
            const raw = window.localStorage.getItem(STORAGE_KEY);
            if (!raw) {
                return emptyConfig();
            }
            return Object.assign(emptyConfig(), JSON.parse(raw));
        } catch (error) {
            // Private mode, disabled storage, or a corrupt value. Customization
            // is a nicety; losing it must never cost the game.
            console.warn('Could not read the customize config:', error);
            return emptyConfig();
        }
    }

    function saveConfig(config) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
        } catch (error) {
            console.warn('Could not save the customize config:', error);
        }
    }

    // '#11a2ff' -> '17 162 255' (space-separated channels for rgb()).
    function hexToChannels(hex) {
        const match = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
        if (!match) {
            return null;
        }
        const value = parseInt(match[1], 16);
        return `${(value >> 16) & 255} ${(value >> 8) & 255} ${value & 255}`;
    }

    // The override CSS the structured controls compose. Only fields that are set
    // emit a declaration, so an empty config yields an empty rule — that is what
    // keeps the default look untouched.
    function buildOverrideCss(config) {
        const lines = [];

        if (config.panelOpacity != null) {
            lines.push(`--panel-opacity: ${config.panelOpacity};`);
        }
        if (config.fontKey && FONT_STACKS[config.fontKey]) {
            lines.push(`--font-ui: ${FONT_STACKS[config.fontKey]};`);
        }
        if (config.textScale != null) {
            lines.push(`--text-scale: ${config.textScale};`);
        }
        if (config.panelBg) {
            if (config.panelBg.mode === 'gradient') {
                const { angle = 135, c1 = '#161d24', c2 = '#0b0d10' } = config.panelBg;
                // Replaces --glass wholesale — a `background` shorthand accepts an
                // image, so the glass floats carry the gradient. The panel opacity
                // slider governs the solid mode; a gradient brings its own colours.
                lines.push(`--glass: linear-gradient(${angle}deg, ${c1}, ${c2});`);
            } else if (config.panelBg.color) {
                const channels = hexToChannels(config.panelBg.color);
                if (channels) {
                    // Only the tint — opacity still flows from --panel-opacity, so a
                    // solid colour and the opacity slider compose.
                    lines.push(`--panel-tint: ${channels};`);
                }
            }
        }
        if (config.accent) {
            lines.push(`--accent: ${config.accent};`);
            // Keep the derived accents in step so hovers and soft fills do not
            // stay the old orange around a recoloured highlight.
            lines.push(`--accent-hover: color-mix(in srgb, ${config.accent}, white 18%);`);
            lines.push(`--accent-soft: color-mix(in srgb, ${config.accent} 16%, transparent);`);
        }

        return lines.length ? `:root {\n  ${lines.join('\n  ')}\n}` : '';
    }

    // Phase B: the per-panel drag offsets, as id-selector transform rules. A
    // panel never dragged emits nothing, so an unconfigured browser's layout is
    // byte-identical. `!important` because the in-game floats are placed by
    // `body:has(...)` rules whose specificity outranks a bare id selector; the
    // rule is injected in <head>, so a saved offset paints on the first frame the
    // panel appears with no flash. The default transform (e.g. the centred chip's
    // translateX(-50%)) is composed in front so the offset adds to it, not
    // replaces it.
    function buildLayoutCss(config) {
        const layout = config.layout || {};
        const lines = [];
        for (const id of Object.keys(DRAGGABLE)) {
            const pos = layout[id];
            if (!pos || (!pos.x && !pos.y)) {
                continue;
            }
            const base = DRAGGABLE[id] ? DRAGGABLE[id] + ' ' : '';
            lines.push(
                `#${id} { transform: ${base}translate(${pos.x}px, ${pos.y}px) !important; }`
            );
        }
        return lines.join('\n');
    }

    // --- Phase C: compose the readouts into the HUD. -----------------------
    //
    // Where each widget started, so it can always be put back: its original
    // parent and the sibling it sat before. Recorded once, the first time the
    // DOM is ready — the elements do not exist when this file first runs in
    // <head>, so recording is deferred to the first applyHud after load.
    const widgetHomes = {};

    function recordHomes() {
        for (const id of Object.keys(WIDGETS)) {
            if (widgetHomes[id]) {
                continue;
            }
            const element = document.getElementById(id);
            if (element) {
                widgetHomes[id] = { parent: element.parentNode, next: element.nextSibling };
            }
        }
    }

    // Return a widget to exactly where it was in the template, stripped of every
    // HUD placement style. Used as the teardown before each re-apply and by both
    // resets, so applyHud is a pure function of the config, not of prior state.
    function restoreHome(id) {
        const element = document.getElementById(id);
        const home = widgetHomes[id];
        if (!element || !home) {
            return;
        }
        element.classList.remove('hud-hidden');
        element.style.position = '';
        element.style.left = '';
        element.style.top = '';
        element.style.zIndex = '';
        const next = home.next && home.next.parentNode === home.parent ? home.next : null;
        if (element.parentNode !== home.parent || element.nextSibling !== next) {
            home.parent.insertBefore(element, next);
        }
    }

    // Build one custom panel's element (its widgets are moved in by applyHud).
    // The delete button and the move handle are inert outside edit mode (CSS),
    // so a composed panel is a plain glass surface during play.
    function createHudPanel(panel) {
        const section = document.createElement('section');
        section.className = 'hud-panel';
        section.dataset.panelId = panel.id;
        section.style.left = (panel.x || 0) + 'px';
        section.style.top = (panel.y || 0) + 'px';

        const head = document.createElement('div');
        head.className = 'hud-panel-head';
        const title = document.createElement('span');
        title.className = 'hud-panel-title';
        title.textContent = 'Panel';
        const del = document.createElement('button');
        del.type = 'button';
        del.className = 'hud-panel-del';
        del.dataset.delPanel = panel.id;
        del.setAttribute('aria-label', 'Delete panel');
        del.textContent = '×';
        head.append(title, del);

        const body = document.createElement('div');
        body.className = 'hud-panel-body';

        section.append(head, body);
        return section;
    }

    // The single HUD apply path. Idempotent: it first tears the composition back
    // to the default DOM (restore every widget, drop every custom panel), then
    // rebuilds from the config. Null-safe, so the early <head> call (when the
    // overlay layer does not exist yet) is a harmless no-op and the real apply
    // runs from initHud once the body is parsed.
    function applyHud(config) {
        const overlays = document.getElementById(HUD_LAYER_ID);
        if (!overlays) {
            return;
        }
        recordHomes();

        // Teardown to the default DOM.
        for (const stale of overlays.querySelectorAll('.hud-panel')) {
            stale.remove();
        }
        for (const id of Object.keys(WIDGETS)) {
            restoreHome(id);
        }

        const hud = config.hud || emptyHud();
        if (hudIsEmpty(hud)) {
            return;   // byte-identical default: nothing is moved or styled.
        }

        const inPanel = new Set();
        for (const panel of hud.panels || []) {
            const section = createHudPanel(panel);
            overlays.appendChild(section);
            const body = section.querySelector('.hud-panel-body');
            for (const widgetId of panel.widgets || []) {
                const element = document.getElementById(widgetId);
                if (element && WIDGETS[widgetId]) {
                    element.style.position = '';
                    element.style.left = '';
                    element.style.top = '';
                    element.style.zIndex = '';
                    body.appendChild(element);
                    inPanel.add(widgetId);
                }
            }
        }

        for (const [id, state] of Object.entries(hud.widgets || {})) {
            const element = document.getElementById(id);
            if (!element || !WIDGETS[id]) {
                continue;
            }
            if (state.hidden) {
                element.classList.add('hud-hidden');
                continue;
            }
            // A free position only applies while the widget is not in a panel.
            if (!inPanel.has(id) && state.x != null && state.y != null) {
                overlays.appendChild(element);
                element.style.position = 'absolute';
                element.style.left = state.x + 'px';
                element.style.top = state.y + 'px';
                element.style.zIndex = 'var(--z-board-overlay)';
            }
        }
    }

    function ensureStyle(id) {
        let element = document.getElementById(id);
        if (!element) {
            element = document.createElement('style');
            element.id = id;
            // Appended to <head> after the linked stylesheets, so an override on
            // :root wins the tie against tokens.css by source order.
            document.head.appendChild(element);
        }
        return element;
    }

    // The single apply path — used by the early boot call and by every live
    // edit. Custom CSS goes in its own element so a syntax error in it can never
    // take the structured overrides down with it.
    function applyConfig(config) {
        ensureStyle(OVERRIDE_STYLE_ID).textContent = buildOverrideCss(config);
        ensureStyle(CUSTOM_CSS_STYLE_ID).textContent = config.customCss || '';
        ensureStyle(LAYOUT_STYLE_ID).textContent = buildLayoutCss(config);
        applyHud(config);
    }

    // --- Apply immediately, before the body paints. -------------------------
    let config = loadConfig();
    applyConfig(config);

    // --- The panel. Wired once the controls exist. --------------------------
    function wirePanel() {
        const panel = document.getElementById('customize-panel');
        const toggle = document.getElementById('customize-toggle');
        const body = document.getElementById('customize-body');
        const closeBtn = document.getElementById('customize-close');
        if (!panel || !toggle || !body) {
            return;
        }

        const el = (id) => document.getElementById(id);
        const opacity = el('cz-opacity');
        const opacityOut = el('cz-opacity-out');
        const font = el('cz-font');
        const scale = el('cz-scale');
        const scaleOut = el('cz-scale-out');
        const bgMode = el('cz-bg-mode');
        const bgColor = el('cz-bg-color');
        const gradRow = el('cz-grad-row');
        const solidRow = el('cz-solid-row');
        const gradAngle = el('cz-grad-angle');
        const gradAngleOut = el('cz-grad-angle-out');
        const gradC1 = el('cz-grad-c1');
        const gradC2 = el('cz-grad-c2');
        const accent = el('cz-accent');
        const custom = el('cz-custom');
        const io = el('cz-io');
        const ioNote = el('cz-io-note');
        const layoutEdit = el('cz-layout-edit');

        // The effective value of a token right now, for seeding a control that
        // has no override yet — so a slider does not lie about where the UI sits.
        const computed = (name) =>
            getComputedStyle(document.documentElement).getPropertyValue(name).trim();

        function commit() {
            applyConfig(config);
            saveConfig(config);
        }

        // Push the current config onto the controls. Called on open so the panel
        // always reflects the live state, including after an Import or Reset.
        function syncControls() {
            const effOpacity = config.panelOpacity != null
                ? config.panelOpacity
                : parseFloat(computed('--panel-opacity')) || 0.62;
            opacity.value = effOpacity;
            opacityOut.textContent = Math.round(effOpacity * 100) + '%';

            font.value = config.fontKey || '';

            const effScale = config.textScale != null
                ? config.textScale
                : parseFloat(computed('--text-scale')) || 1;
            scale.value = effScale;
            scaleOut.textContent = Math.round(effScale * 100) + '%';

            const bg = config.panelBg || {};
            bgMode.value = bg.mode || 'solid';
            bgColor.value = bg.color || '#161d24';
            gradAngle.value = bg.angle != null ? bg.angle : 135;
            gradAngleOut.textContent = gradAngle.value + '°';
            gradC1.value = bg.c1 || '#161d24';
            gradC2.value = bg.c2 || '#0b0d10';
            solidRow.classList.toggle('hidden', bgMode.value === 'gradient');
            gradRow.classList.toggle('hidden', bgMode.value !== 'gradient');

            accent.value = config.accent || (computed('--accent') || '#f18a4b');
            custom.value = config.customCss || '';
            if (layoutEdit) {
                layoutEdit.checked = document.body.classList.contains('layout-edit');
            }
            buildWidgetChecklist();
        }

        // Keep the HUD config well-formed before an edit touches it.
        function ensureHud() {
            if (!config.hud || typeof config.hud !== 'object') {
                config.hud = emptyHud();
            }
            if (!config.hud.widgets || typeof config.hud.widgets !== 'object') {
                config.hud.widgets = {};
            }
            if (!Array.isArray(config.hud.panels)) {
                config.hud.panels = [];
            }
        }

        // The per-widget show/hide checklist: one row per registered readout,
        // ticked while it is shown. A checklist rather than a tag injected into
        // each widget because #turn-banner's renderer rewrites its own innerHTML
        // and would wipe an injected control on the next board update.
        function buildWidgetChecklist() {
            const list = el('cz-widget-list');
            if (!list) {
                return;
            }
            list.textContent = '';
            const widgets = (config.hud && config.hud.widgets) || {};
            for (const [id, label] of Object.entries(WIDGETS)) {
                const row = document.createElement('label');
                row.className = 'cz-widget-row';
                const checkbox = document.createElement('input');
                checkbox.type = 'checkbox';
                checkbox.dataset.widgetId = id;
                checkbox.checked = !(widgets[id] && widgets[id].hidden);
                checkbox.addEventListener('change', () => {
                    ensureHud();
                    const state = config.hud.widgets[id] || (config.hud.widgets[id] = {});
                    if (checkbox.checked) {
                        delete state.hidden;
                        if (Object.keys(state).length === 0) {
                            delete config.hud.widgets[id];
                        }
                    } else {
                        state.hidden = true;
                    }
                    commit();
                });
                const name = document.createElement('span');
                name.textContent = label;
                row.append(checkbox, name);
                list.appendChild(row);
            }
        }

        opacity.addEventListener('input', () => {
            config.panelOpacity = parseFloat(opacity.value);
            opacityOut.textContent = Math.round(config.panelOpacity * 100) + '%';
            commit();
        });
        font.addEventListener('change', () => {
            config.fontKey = font.value || null;
            commit();
        });
        scale.addEventListener('input', () => {
            config.textScale = parseFloat(scale.value);
            scaleOut.textContent = Math.round(config.textScale * 100) + '%';
            commit();
        });

        function readPanelBg() {
            if (bgMode.value === 'gradient') {
                config.panelBg = {
                    mode: 'gradient',
                    angle: parseInt(gradAngle.value, 10),
                    c1: gradC1.value,
                    c2: gradC2.value,
                };
            } else {
                config.panelBg = { mode: 'solid', color: bgColor.value };
            }
            commit();
        }
        bgMode.addEventListener('change', () => {
            solidRow.classList.toggle('hidden', bgMode.value === 'gradient');
            gradRow.classList.toggle('hidden', bgMode.value !== 'gradient');
            readPanelBg();
        });
        bgColor.addEventListener('input', readPanelBg);
        gradAngle.addEventListener('input', () => {
            gradAngleOut.textContent = gradAngle.value + '°';
            readPanelBg();
        });
        gradC1.addEventListener('input', readPanelBg);
        gradC2.addEventListener('input', readPanelBg);
        accent.addEventListener('input', () => {
            config.accent = accent.value;
            commit();
        });
        custom.addEventListener('input', () => {
            config.customCss = custom.value;
            commit();
        });

        // --- Edit layout mode + drag machinery. ------------------------------
        // The toggle is transient (not persisted): it turns the panels into
        // draggable outlined tiles while on, and hands normal play back the
        // moment it is off. Only the resulting offsets persist.
        if (layoutEdit) {
            layoutEdit.addEventListener('change', () => {
                document.body.classList.toggle('layout-edit', layoutEdit.checked);
            });
        }

        const resetLayoutBtn = el('cz-reset-layout');
        if (resetLayoutBtn) {
            resetLayoutBtn.addEventListener('click', () => {
                // Scoped to the layout field only — the Phase-A appearance config
                // (accent, opacity, custom CSS…) is left exactly as it is.
                config.layout = {};
                commit();
                if (ioNote) {
                    ioNote.textContent = 'Panels returned to their default positions.';
                }
            });
        }

        wireDrag(commit);
        wireHud(commit);

        el('cz-reset').addEventListener('click', () => {
            config = emptyConfig();
            try {
                window.localStorage.removeItem(STORAGE_KEY);
            } catch (error) {
                console.warn('Could not clear the customize config:', error);
            }
            applyConfig(config);
            syncControls();
            if (ioNote) {
                ioNote.textContent = 'Reset to the default look.';
            }
        });

        el('cz-export').addEventListener('click', async () => {
            const text = JSON.stringify(config, null, 2);
            io.value = text;
            try {
                await navigator.clipboard.writeText(text);
                ioNote.textContent = 'Copied. Paste it somewhere to keep it.';
            } catch (error) {
                console.warn('Could not copy the config:', error);
                io.select();
                ioNote.textContent = 'Selected — press Ctrl+C to copy.';
            }
        });

        el('cz-import').addEventListener('click', () => {
            try {
                const parsed = JSON.parse(io.value);
                if (!parsed || typeof parsed !== 'object') {
                    throw new Error('not an object');
                }
                config = Object.assign(emptyConfig(), parsed);
                commit();
                syncControls();
                ioNote.textContent = 'Imported.';
            } catch (error) {
                console.warn('Could not import the config:', error);
                ioNote.textContent = 'That is not a valid config — check the JSON.';
            }
        });

        // Make each floating overlay draggable while Edit layout mode is on. The
        // listeners are attached once but do nothing unless the body carries the
        // `layout-edit` class, so play outside edit mode is untouched. Pointer
        // events cover mouse and touch with one path.
        function wireDrag(commitOffset) {
            for (const id of Object.keys(DRAGGABLE)) {
                const element = document.getElementById(id);
                if (!element) {
                    continue;
                }
                element.addEventListener('pointerdown', (event) => {
                    if (!document.body.classList.contains('layout-edit')) {
                        return;
                    }
                    // The grab must not double as a click on the control beneath.
                    event.preventDefault();
                    event.stopPropagation();

                    if (!config.layout || typeof config.layout !== 'object') {
                        config.layout = {};
                    }
                    const startRect = element.getBoundingClientRect();
                    const startX = event.clientX;
                    const startY = event.clientY;
                    const current = config.layout[id] || {};
                    const baseX = current.x || 0;
                    const baseY = current.y || 0;

                    // Clamp the pointer delta so KEEP_ON_SCREEN px of the panel
                    // stays inside every viewport edge — never lost off-screen.
                    const viewWidth = window.innerWidth;
                    const viewHeight = window.innerHeight;
                    const clampDx = (dx) => Math.max(
                        KEEP_ON_SCREEN - startRect.right,
                        Math.min(viewWidth - KEEP_ON_SCREEN - startRect.left, dx),
                    );
                    const clampDy = (dy) => Math.max(
                        KEEP_ON_SCREEN - startRect.bottom,
                        Math.min(viewHeight - KEEP_ON_SCREEN - startRect.top, dy),
                    );

                    const move = (moveEvent) => {
                        const dx = clampDx(moveEvent.clientX - startX);
                        const dy = clampDy(moveEvent.clientY - startY);
                        config.layout[id] = { x: baseX + dx, y: baseY + dy };
                        applyConfig(config);
                    };
                    const up = () => {
                        element.removeEventListener('pointermove', move);
                        element.removeEventListener('pointerup', up);
                        element.removeEventListener('pointercancel', up);
                        try {
                            element.releasePointerCapture(event.pointerId);
                        } catch (error) {
                            // Capture already released; nothing to undo.
                        }
                        commitOffset();
                    };
                    try {
                        element.setPointerCapture(event.pointerId);
                    } catch (error) {
                        // No pointer capture here; move/up still reach the element.
                    }
                    element.addEventListener('pointermove', move);
                    element.addEventListener('pointerup', up);
                    element.addEventListener('pointercancel', up);
                });
            }
        }

        // --- Phase C: the HUD builder. --------------------------------------
        // Tag the registered readouts, compose the saved HUD on load, and wire
        // the edit-mode affordances: drag a widget to a free spot or onto a
        // panel, create/move/delete panels, and hide/show via the checklist.
        function wireHud(commit) {
            for (const id of Object.keys(WIDGETS)) {
                const element = document.getElementById(id);
                if (element) {
                    element.classList.add('hud-widget');
                    wireWidgetDrag(element, id, commit);
                }
            }
            recordHomes();
            // Compose whatever was saved, now that the DOM (and the overlay
            // layer) exists — the early <head> apply could not reach it.
            applyHud(config);

            const overlays = document.getElementById(HUD_LAYER_ID);
            if (overlays) {
                wirePanelControls(overlays, commit);
            }

            const addPanelBtn = el('cz-hud-add-panel');
            if (addPanelBtn) {
                addPanelBtn.addEventListener('click', () => {
                    ensureHud();
                    const id = 'p' + Date.now().toString(36);
                    // In a little from the corner so its header is easy to grab.
                    config.hud.panels.push({ id, x: 24, y: 24, widgets: [] });
                    commit();
                    // Reveal the fresh panel by turning edit mode on.
                    document.body.classList.add('layout-edit');
                    if (layoutEdit) {
                        layoutEdit.checked = true;
                    }
                    if (ioNote) {
                        ioNote.textContent = 'Panel added — drag readouts into it.';
                    }
                });
            }

            const resetHudBtn = el('cz-reset-hud');
            if (resetHudBtn) {
                resetHudBtn.addEventListener('click', () => {
                    // Scoped to the composition only: the Phase-A appearance and
                    // the Phase-B panel offsets are left exactly as they are.
                    config.hud = emptyHud();
                    commit();
                    buildWidgetChecklist();
                    if (ioNote) {
                        ioNote.textContent = 'HUD returned to the default readouts.';
                    }
                });
            }
        }

        // Grab a whole readout in edit mode and either drop it onto a custom
        // panel (it docks) or onto free board space (it floats there). The same
        // live element is moved — never a copy — so its renderer keeps writing
        // into it by id exactly as before.
        function wireWidgetDrag(element, id, commit) {
            element.addEventListener('pointerdown', (event) => {
                if (!document.body.classList.contains('layout-edit')) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                ensureHud();

                const startRect = element.getBoundingClientRect();
                const grabX = event.clientX - startRect.left;
                const grabY = event.clientY - startRect.top;

                // Lift it onto the viewport so it follows the pointer over
                // everything, clear of the overlay layer's overflow clip.
                element.classList.add('hud-dragging');
                element.style.position = 'fixed';
                element.style.width = startRect.width + 'px';
                element.style.left = startRect.left + 'px';
                element.style.top = startRect.top + 'px';
                element.style.zIndex = '9999';
                element.style.pointerEvents = 'none';
                document.body.appendChild(element);

                let dropPanel = null;
                const move = (moveEvent) => {
                    element.style.left = (moveEvent.clientX - grabX) + 'px';
                    element.style.top = (moveEvent.clientY - grabY) + 'px';
                    const under = document.elementFromPoint(moveEvent.clientX, moveEvent.clientY);
                    const panelEl = under && under.closest ? under.closest('.hud-panel') : null;
                    if (panelEl !== dropPanel) {
                        if (dropPanel) {
                            dropPanel.classList.remove('hud-drop');
                        }
                        dropPanel = panelEl;
                        if (dropPanel) {
                            dropPanel.classList.add('hud-drop');
                        }
                    }
                };
                const up = (upEvent) => {
                    window.removeEventListener('pointermove', move);
                    window.removeEventListener('pointerup', up);
                    if (dropPanel) {
                        dropPanel.classList.remove('hud-drop');
                    }

                    // Out of any panel it currently sits in, first.
                    for (const panel of config.hud.panels) {
                        panel.widgets = (panel.widgets || []).filter((w) => w !== id);
                    }
                    const state = config.hud.widgets[id] || (config.hud.widgets[id] = {});

                    if (dropPanel && dropPanel.dataset.panelId) {
                        const target = config.hud.panels.find(
                            (p) => p.id === dropPanel.dataset.panelId,
                        );
                        if (target) {
                            target.widgets = target.widgets || [];
                            target.widgets.push(id);
                        }
                        delete state.x;
                        delete state.y;
                    } else {
                        // Free position, in overlay-relative pixels.
                        const overlays = document.getElementById(HUD_LAYER_ID);
                        const rect = overlays
                            ? overlays.getBoundingClientRect()
                            : { left: 0, top: 0 };
                        state.x = Math.round(Math.max(0, upEvent.clientX - grabX - rect.left));
                        state.y = Math.round(Math.max(0, upEvent.clientY - grabY - rect.top));
                    }
                    if (Object.keys(state).length === 0) {
                        delete config.hud.widgets[id];
                    }

                    // Drop the lift styles; applyHud (via commit) re-places it.
                    element.classList.remove('hud-dragging');
                    element.style.pointerEvents = '';
                    element.style.width = '';
                    element.style.position = '';
                    element.style.left = '';
                    element.style.top = '';
                    element.style.zIndex = '';
                    commit();
                };
                window.addEventListener('pointermove', move);
                window.addEventListener('pointerup', up);
            });
        }

        // Delete and move for custom panels, by delegation on the overlay layer:
        // panels are rebuilt on every applyHud, so a per-element listener would
        // not survive. Inert outside edit mode.
        function wirePanelControls(overlays, commit) {
            overlays.addEventListener('click', (event) => {
                if (!document.body.classList.contains('layout-edit')) {
                    return;
                }
                const del = event.target.closest
                    ? event.target.closest('.hud-panel-del')
                    : null;
                if (!del) {
                    return;
                }
                event.preventDefault();
                ensureHud();
                const panelId = del.dataset.delPanel;
                config.hud.panels = config.hud.panels.filter((p) => p.id !== panelId);
                commit();
            });

            overlays.addEventListener('pointerdown', (event) => {
                if (!document.body.classList.contains('layout-edit')) {
                    return;
                }
                const target = event.target;
                if (target.closest && target.closest('.hud-panel-del')) {
                    return;
                }
                const head = target.closest ? target.closest('.hud-panel-head') : null;
                if (!head) {
                    return;
                }
                const section = head.closest('.hud-panel');
                if (!section) {
                    return;
                }
                event.preventDefault();
                event.stopPropagation();
                ensureHud();
                const panel = config.hud.panels.find(
                    (p) => p.id === section.dataset.panelId,
                );
                if (!panel) {
                    return;
                }
                const startX = event.clientX;
                const startY = event.clientY;
                const baseX = panel.x || 0;
                const baseY = panel.y || 0;
                const move = (moveEvent) => {
                    panel.x = baseX + (moveEvent.clientX - startX);
                    panel.y = baseY + (moveEvent.clientY - startY);
                    section.style.left = panel.x + 'px';
                    section.style.top = panel.y + 'px';
                };
                const up = () => {
                    window.removeEventListener('pointermove', move);
                    window.removeEventListener('pointerup', up);
                    commit();
                };
                window.addEventListener('pointermove', move);
                window.addEventListener('pointerup', up);
            });
        }

        // --- open / close: a disclosure, like the changelog pill. ------------
        const isOpen = () => toggle.getAttribute('aria-expanded') === 'true';
        function open() {
            syncControls();
            body.classList.remove('hidden');
            toggle.setAttribute('aria-expanded', 'true');
        }
        function close(restoreFocus) {
            body.classList.add('hidden');
            toggle.setAttribute('aria-expanded', 'false');
            if (ioNote) {
                ioNote.textContent = '';
            }
            if (restoreFocus) {
                toggle.focus();
            }
        }
        toggle.addEventListener('click', () => (isOpen() ? close() : open()));
        if (closeBtn) {
            closeBtn.addEventListener('click', () => close(true));
        }
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape' && isOpen()) {
                close(true);
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wirePanel);
    } else {
        wirePanel();
    }
})();
