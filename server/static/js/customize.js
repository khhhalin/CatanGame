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
        };
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
