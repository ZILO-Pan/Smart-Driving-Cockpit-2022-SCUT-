(function () {
    const CANVAS_W = 3840;
    const CANVAS_H = 590;

    function scaleCanvas() {
        const canvas = document.getElementById('canvas');
        if (!canvas) return;
        const scaleX = window.innerWidth / CANVAS_W;
        const scaleY = window.innerHeight / CANVAS_H;
        const scale = Math.min(scaleX, scaleY);
        canvas.style.transform = `translate(-50%, -50%) scale(${scale})`;
    }

    // ─── Lockscreen ──────────────────────────────────────────
    const lockscreen = document.getElementById('lockscreen');
    let idleTimer = null;
    const IDLE_TIMEOUT = 30000;

    function dismissLockscreen() {
        lockscreen.classList.add('dismissed');
        resetIdleTimer();
    }

    function showLockscreen() {
        lockscreen.classList.remove('dismissed');
    }

    function resetIdleTimer() {
        clearTimeout(idleTimer);
        idleTimer = setTimeout(showLockscreen, IDLE_TIMEOUT);
    }

    lockscreen.addEventListener('click', dismissLockscreen);

    // Reset idle timer on any interaction within canvas
    document.getElementById('canvas').addEventListener('pointerdown', () => {
        if (lockscreen.classList.contains('dismissed')) {
            resetIdleTimer();
        }
    });

    function updateLockClock() {
        const now = new Date();
        const timeEl = document.getElementById('lock-time');
        const dateEl = document.getElementById('lock-date');
        if (timeEl) {
            timeEl.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        }
        if (dateEl) {
            dateEl.textContent = now.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        }
    }

    // ─── Dock ────────────────────────────────────────────────
    const servicePanel = document.getElementById('service-panel');
    const unityOverlay = document.getElementById('unity-overlay');
    const zoneLeft = document.querySelector('.zone-left');
    const zoneCenter = document.querySelector('.zone-center');
    const zoneRight = document.querySelector('.zone-right');

    const dockNav = document.getElementById('dock-nav');
    const dockAdas = document.getElementById('dock-adas');
    const dockAi = document.getElementById('dock-ai');
    const dockService = document.getElementById('dock-service');
    const dockCabin = document.getElementById('dock-cabin');
    const dock3d = document.getElementById('dock-3d');

    let unityLoaded = false;

    // Left zone (ADAS)
    dockAdas.classList.add('active');
    dockAdas.addEventListener('click', () => {
        const hidden = zoneLeft.classList.toggle('hidden');
        dockAdas.classList.toggle('active', !hidden);
    });

    // Center zone (Nav)
    dockNav.classList.add('active');
    dockNav.addEventListener('click', () => {
        const hidden = zoneCenter.classList.toggle('hidden');
        dockNav.classList.toggle('active', !hidden);
    });

    // Right zone (Cabin/Entertainment)
    dockCabin.classList.add('active');
    dockCabin.addEventListener('click', () => {
        const hidden = zoneRight.classList.toggle('hidden');
        dockCabin.classList.toggle('active', !hidden);
    });

    // Services panel
    dockService.addEventListener('click', () => {
        const open = servicePanel.classList.toggle('open');
        dockService.classList.toggle('active', open);
    });

    // 3D Unity
    dock3d.addEventListener('click', () => {
        const isOpen = unityOverlay.classList.toggle('active');
        dock3d.classList.toggle('active', isOpen);
        if (isOpen && !unityLoaded) {
            loadUnity();
            unityLoaded = true;
        }
    });

    document.getElementById('service-close-btn').addEventListener('click', () => {
        servicePanel.classList.remove('open');
        dockService.classList.remove('active');
    });

    // ─── Unity Loading ───────────────────────────────────────
    function loadUnity() {
        if (typeof createUnityInstance === 'undefined') {
            const loading = document.getElementById('unity-loading');
            const textEl = loading.querySelector('.unity-loading-text');
            textEl.textContent = 'Unity Build not found';
            return;
        }

        const buildUrl = '/static/unity/ai-car-scene/Build';
        const config = {
            dataUrl: buildUrl + '/AI4HMI.data.gz',
            frameworkUrl: buildUrl + '/AI4HMI.framework.js.gz',
            codeUrl: buildUrl + '/AI4HMI.wasm.gz',
            streamingAssetsUrl: '/static/unity/ai-car-scene/StreamingAssets',
            companyName: 'DefaultCompany',
            productName: 'AI4HMI',
            productVersion: '1.0',
        };

        const unityCanvas = document.getElementById('unity-canvas');
        const loading = document.getElementById('unity-loading');
        const progressBar = document.getElementById('unity-progress-bar');

        createUnityInstance(unityCanvas, config, (progress) => {
            progressBar.style.width = (progress * 100) + '%';
        }).then((instance) => {
            window.unityInstance = instance;
            loading.classList.add('hidden');
            setTimeout(() => loading.remove(), 600);
            setupHMIBridge(instance);
        }).catch((err) => {
            console.error('Unity load failed:', err);
            const textEl = loading.querySelector('.unity-loading-text');
            textEl.textContent = 'Failed to load 3D scene';
        });
    }

    // ─── HMI Bridge ──────────────────────────────────────────
    function setupHMIBridge(instance) {
        window.HMI = {
            sendCommand(action, target, params) {
                if (!instance) return;
                const cmd = { action, target: target || '', paramsJson: params ? JSON.stringify(params) : '' };
                instance.SendMessage('HMIController', 'ExecuteCommand', JSON.stringify(cmd));
            },
            switchCamera(view) { this.sendCommand('switchCamera', view); },
            togglePart(partId) { this.sendCommand('togglePart', partId); },
            openPart(partId) { this.sendCommand('openPart', partId); },
            closePart(partId) { this.sendCommand('closePart', partId); },
            rotateCarTo(angle) { this.sendCommand('rotateCar', 'absolute', { angle }); },
            rotateCarBy(angle) { this.sendCommand('rotateCar', 'relative', { angle }); },
            resetCarRotation() { this.sendCommand('rotateCar', 'reset'); },
            getState() { this.sendCommand('getState', 'all'); },
        };

        window.HMIBus = {
            listeners: [],
            on(fn) { this.listeners.push(fn); },
            off(fn) { this.listeners = this.listeners.filter(l => l !== fn); },
            emit(evt) { this.listeners.forEach(fn => fn(evt)); }
        };
    }

    // ─── Audio ───────────────────────────────────────────────
    const audioHello = new Audio('/static/videos/Hello.mp3');
    const audioBye = new Audio('/static/videos/Bye.mp3');
    let currentView = 'default';

    window.OnUnityEvent = function (jsonStr) {
        try {
            const evt = JSON.parse(jsonStr);
            console.log('[Unity Event]', evt);
            if (window.HMIBus) window.HMIBus.emit(evt);

            if (evt.eventType === 'cameraTransitionStart') {
                if (currentView === 'astronaut' && evt.target !== 'astronaut') {
                    audioBye.currentTime = 0;
                    audioBye.play();
                }
            }
            if (evt.eventType === 'cameraTransitionEnd') {
                currentView = evt.target;
                if (evt.target === 'astronaut') {
                    audioHello.currentTime = 0;
                    audioHello.play();
                }
            }
        } catch (e) {
            console.error('Failed to parse Unity event:', e);
        }
    };

    // ─── ADAS Canvas ─────────────────────────────────────────
    function initADAS() {
        const canvas = document.getElementById('adas-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        function resize() {
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
        }
        resize();

        let frame = 0;
        function draw() {
            const w = canvas.width;
            const h = canvas.height;
            if (w === 0 || h === 0) { requestAnimationFrame(draw); return; }
            ctx.clearRect(0, 0, w, h);

            // Road surface
            const roadL = w * 0.2;
            const roadR = w * 0.8;
            ctx.fillStyle = 'rgba(255,255,255,0.03)';
            ctx.fillRect(roadL, 0, roadR - roadL, h);

            // Lane markings (dashed center)
            ctx.strokeStyle = 'rgba(255,255,255,0.25)';
            ctx.setLineDash([12, 12]);
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(w * 0.5, 0);
            ctx.lineTo(w * 0.5, h);
            ctx.stroke();

            // Lane edges (solid)
            ctx.strokeStyle = 'rgba(255,255,255,0.4)';
            ctx.setLineDash([]);
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.moveTo(roadL, 0); ctx.lineTo(roadL, h);
            ctx.moveTo(roadR, 0); ctx.lineTo(roadR, h);
            ctx.stroke();

            // Ego vehicle
            const egoW = w * 0.1;
            const egoH = h * 0.13;
            const egoX = w * 0.5 - egoW / 2;
            const egoY = h * 0.75;
            ctx.fillStyle = 'rgba(77, 216, 229, 0.7)';
            roundRect(ctx, egoX, egoY, egoW, egoH, 3);
            ctx.fill();

            // Surrounding vehicles
            const cars = [
                { x: 0.62, y: 0.3 },
                { x: 0.35, y: 0.15 },
                { x: 0.65, y: 0.6 },
            ];
            cars.forEach((c, i) => {
                const cy = h * c.y + Math.sin(frame * 0.015 + i * 2) * 4;
                ctx.fillStyle = 'rgba(245, 166, 35, 0.6)';
                ctx.beginPath();
                roundRect(ctx, w * c.x, cy, egoW * 0.8, egoH * 0.8, 2);
                ctx.fill();
            });

            // Sensor cone
            ctx.fillStyle = 'rgba(77, 216, 229, 0.04)';
            ctx.beginPath();
            ctx.moveTo(w * 0.5, egoY);
            ctx.lineTo(w * 0.2, 0);
            ctx.lineTo(w * 0.8, 0);
            ctx.closePath();
            ctx.fill();

            frame++;
            requestAnimationFrame(draw);
        }
        draw();
    }

    // ─── Nav Canvas ──────────────────────────────────────────
    function initNav() {
        const canvas = document.getElementById('nav-canvas');
        if (!canvas) return;
        const ctx = canvas.getContext('2d');

        function resize() {
            const rect = canvas.parentElement.getBoundingClientRect();
            canvas.width = rect.width;
            canvas.height = rect.height;
        }
        resize();

        let frame = 0;
        function draw() {
            const w = canvas.width;
            const h = canvas.height;
            if (w === 0 || h === 0) { requestAnimationFrame(draw); return; }
            ctx.clearRect(0, 0, w, h);

            // Grid lines (road network)
            ctx.strokeStyle = 'rgba(255,255,255,0.06)';
            ctx.lineWidth = 1;
            for (let x = 0; x < w; x += 60) {
                ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
            }
            for (let y = 0; y < h; y += 60) {
                ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
            }

            // Main road
            ctx.strokeStyle = 'rgba(255,255,255,0.15)';
            ctx.lineWidth = 8;
            ctx.lineCap = 'round';
            ctx.beginPath();
            ctx.moveTo(w * 0.5, h);
            ctx.quadraticCurveTo(w * 0.5, h * 0.5, w * 0.7, h * 0.2);
            ctx.lineTo(w * 0.8, 0);
            ctx.stroke();

            // Route highlight
            ctx.strokeStyle = 'rgba(77, 216, 229, 0.5)';
            ctx.lineWidth = 4;
            ctx.beginPath();
            ctx.moveTo(w * 0.5, h);
            ctx.quadraticCurveTo(w * 0.5, h * 0.5, w * 0.7, h * 0.2);
            ctx.lineTo(w * 0.8, 0);
            ctx.stroke();

            // Self position (pulsing dot)
            const selfX = w * 0.5;
            const selfY = h * 0.85;
            const pulse = 1 + Math.sin(frame * 0.05) * 0.3;
            ctx.fillStyle = 'rgba(77, 216, 229, 0.8)';
            ctx.beginPath();
            ctx.arc(selfX, selfY, 6 * pulse, 0, Math.PI * 2);
            ctx.fill();

            // Glow
            ctx.fillStyle = 'rgba(77, 216, 229, 0.15)';
            ctx.beginPath();
            ctx.arc(selfX, selfY, 14 * pulse, 0, Math.PI * 2);
            ctx.fill();

            frame++;
            requestAnimationFrame(draw);
        }
        draw();
    }

    function roundRect(ctx, x, y, w, h, r) {
        ctx.beginPath();
        ctx.moveTo(x + r, y);
        ctx.lineTo(x + w - r, y);
        ctx.quadraticCurveTo(x + w, y, x + w, y + r);
        ctx.lineTo(x + w, y + h - r);
        ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
        ctx.lineTo(x + r, y + h);
        ctx.quadraticCurveTo(x, y + h, x, y + h - r);
        ctx.lineTo(x, y + r);
        ctx.quadraticCurveTo(x, y, x + r, y);
        ctx.closePath();
    }

    // ─── Clock ───────────────────────────────────────────────
    function updateClock() {
        const el = document.getElementById('main-time');
        if (el) {
            const now = new Date();
            el.textContent = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        }
        updateLockClock();
    }

    // ─── Music Player ────────────────────────────────────────
    const playlist = [
        { title: 'Starboy', artist: 'The Weeknd', src: '/static/media/starboy.mp3', cover: '/static/media/Starboy.jpg' },
        { title: 'How You Like That', artist: 'BLACKPINK', src: '/static/media/how you like that.mp3', cover: '/static/media/How you like that.jpg' },
        { title: '晴天', artist: '周杰伦', src: '/static/media/晴天.mp3', cover: '/static/media/Jay.jpg' },
        { title: 'Handlebars', artist: 'Jennie', src: '/static/media/handlebars.mp3', cover: '/static/media/Ruby.jpg' },
        { title: 'Born Again', artist: 'Lisa', src: '/static/media/born again.mp3', cover: '/static/media/Alter Ego.jpg' },
        { title: 'Toxic Till The End', artist: 'ROSÉ', src: '/static/media/toxic till the end.mp3', cover: '/static/media/rosie.jpg' },
    ];

    let currentTrack = 0;
    let isPlaying = false;
    const audio = new Audio();

    function loadTrack(index) {
        currentTrack = index;
        const track = playlist[index];
        audio.src = track.src;
        const img = document.getElementById('album-img');
        const title = document.getElementById('player-title');
        const artist = document.getElementById('player-artist');
        if (img) img.src = track.cover;
        if (title) title.textContent = track.title;
        if (artist) artist.textContent = track.artist;
    }

    function togglePlay() {
        if (isPlaying) {
            audio.pause();
        } else {
            audio.play();
        }
        isPlaying = !isPlaying;
        const btn = document.getElementById('btn-play');
        if (btn) btn.textContent = isPlaying ? '⏸' : '▶';
    }

    function nextTrack() {
        currentTrack = (currentTrack + 1) % playlist.length;
        loadTrack(currentTrack);
        if (isPlaying) audio.play();
    }

    function prevTrack() {
        currentTrack = (currentTrack - 1 + playlist.length) % playlist.length;
        loadTrack(currentTrack);
        if (isPlaying) audio.play();
    }

    audio.addEventListener('ended', nextTrack);
    loadTrack(0);

    // Expose for AI control
    window.MediaControl = {
        play() { if (!isPlaying) togglePlay(); },
        pause() { if (isPlaying) togglePlay(); },
        next() { nextTrack(); },
        prev() { prevTrack(); },
        playTrack(index) { loadTrack(index); if (!isPlaying) togglePlay(); else audio.play(); },
    };

    // ─── Right Zone Card Manager ─────────────────────────────
    const rightStrip = document.getElementById('right-strip');
    const MAX_SLOTS = 4;
    let cards = []; // { id, slots, element }
    let musicOpen = false;
    let bilibiliOpen = false;

    const musicHTML = `
        <div class="music-inner">
            <div class="album-cover" id="album-cover"><img src="/static/media/Starboy.jpg" alt="" id="album-img"></div>
            <span class="player-title" id="player-title">Starboy</span>
            <span class="player-artist" id="player-artist">The Weeknd</span>
            <div class="player-controls">
                <button class="ctrl-btn" id="btn-prev">⏮</button>
                <button class="ctrl-btn ctrl-play" id="btn-play">▶</button>
                <button class="ctrl-btn" id="btn-next">⏭</button>
            </div>
        </div>`;

    const bilibiliHTML = `
        <div class="bilibili-inner">
            <span class="bilibili-label">Bilibili: Recommend</span>
            <div class="bilibili-scroll">
                <img class="bili-poster" src="/static/media/Huntrix.jpg" alt="">
                <img class="bili-poster" src="/static/media/Interstellar.jpg" alt="">
                <img class="bili-poster" src="/static/media/Faerwell My Concubine.jpg" alt="">
                <img class="bili-poster" src="/static/media/The Devil wears Prrada.jpg" alt="">
                <img class="bili-poster" src="/static/media/Nghesieu DE.jpg" alt="">
            </div>
        </div>`;

    const serviceTemplates = {
        alipay: `<img class="service-card-img" src="/static/media/alipay.jpg" alt="Alipay">`,
        ctrip: `<img class="service-card-img" src="/static/media/Ctrip.png" alt="Ctrip">`,
        news: `<img class="service-card-img" src="/static/media/News.png" alt="News">`,
        parking: `<div class="parking-ui"><span class="card-title">Parking — B2</span><div class="parking-slot-grid"><div class="parking-slot">A1</div><div class="parking-slot occupied">A2</div><div class="parking-slot">A3</div><div class="parking-slot occupied">A4</div><div class="parking-slot">B1</div><div class="parking-slot">B2</div><div class="parking-slot occupied">B3</div><div class="parking-slot">B4</div></div></div>`,
        charging: `<div class="charging-ui"><span class="card-title">Charging Stations</span><div class="charging-stations"><div class="charging-station"><span class="station-icon">⚡</span><div class="station-info"><span class="station-name">Tesla Supercharger</span><span class="station-detail">120kW · 0.8km</span></div><span class="station-status">Available</span></div><div class="charging-station"><span class="station-icon">⚡</span><div class="station-info"><span class="station-name">State Grid</span><span class="station-detail">60kW · 1.2km</span></div><span class="station-status">Available</span></div></div></div>`,
    };

    function totalSlots() {
        return cards.reduce((sum, c) => sum + c.slots, 0);
    }

    function removeCard(id) {
        const idx = cards.findIndex(c => c.id === id);
        if (idx === -1) return;
        const entry = cards[idx];
        // Step 1: slide down + fade out
        entry.element.classList.add('leaving');
        // Step 2: after slide finishes, collapse width so others fill in
        setTimeout(() => entry.element.classList.add('collapsing'), 350);
        // Step 3: remove from DOM
        setTimeout(() => entry.element.remove(), 750);
        cards.splice(idx, 1);
        if (id === 'music') musicOpen = false;
        if (id === 'bilibili') bilibiliOpen = false;
        if (id === 'combo') { musicOpen = false; bilibiliOpen = false; }
        rebindPlayerButtons();
    }

    function addCard(id, slots, innerHTML, extraClass) {
        // Remove if already exists
        if (cards.find(c => c.id === id)) {
            removeCard(id);
            return;
        }

        // Make room — remove from right (end of array) until fits
        while (totalSlots() + slots > MAX_SLOTS && cards.length > 0) {
            removeCard(cards[cards.length - 1].id);
        }

        const el = document.createElement('div');
        el.className = 'glass-card slot-card entering' + (slots === 2 ? ' slot-double' : '') + (extraClass ? ' ' + extraClass : '');
        el.dataset.cardId = id;
        el.innerHTML = `<button class="card-close">✕</button>` + innerHTML;

        // Insert at beginning (left)
        rightStrip.prepend(el);
        cards.unshift({ id, slots, element: el });

        // Animate in
        requestAnimationFrame(() => {
            requestAnimationFrame(() => el.classList.remove('entering'));
        });

        // Close button
        el.querySelector('.card-close').addEventListener('click', () => removeCard(id));

        rebindPlayerButtons();
    }

    function rebindPlayerButtons() {
        const btnPlay = document.getElementById('btn-play');
        const btnNext = document.getElementById('btn-next');
        const btnPrev = document.getElementById('btn-prev');
        if (btnPlay) {
            btnPlay.onclick = togglePlay;
            btnPlay.textContent = isPlaying ? '⏸' : '▶';
        }
        if (btnNext) btnNext.onclick = nextTrack;
        if (btnPrev) btnPrev.onclick = prevTrack;
        // Sync track display to DOM
        const track = playlist[currentTrack];
        const img = document.getElementById('album-img');
        const title = document.getElementById('player-title');
        const artist = document.getElementById('player-artist');
        if (img) img.src = track.cover;
        if (title) title.textContent = track.title;
        if (artist) artist.textContent = track.artist;
    }

    function handleMusicBilibili() {
        // If both should be open, merge into combo
        if (musicOpen && bilibiliOpen) {
            // Remove separate ones if they exist
            if (cards.find(c => c.id === 'music')) removeCard('music');
            if (cards.find(c => c.id === 'bilibili')) removeCard('bilibili');
            if (!cards.find(c => c.id === 'combo')) {
                addCard('combo', 2, `<div class="combo-inner">${musicHTML}${bilibiliHTML}</div>`);
            }
        } else if (musicOpen && !bilibiliOpen) {
            if (cards.find(c => c.id === 'combo')) removeCard('combo');
            if (!cards.find(c => c.id === 'music')) addCard('music', 1, musicHTML);
        } else if (!musicOpen && bilibiliOpen) {
            if (cards.find(c => c.id === 'combo')) removeCard('combo');
            if (!cards.find(c => c.id === 'bilibili')) addCard('bilibili', 2, bilibiliHTML);
        } else {
            if (cards.find(c => c.id === 'combo')) removeCard('combo');
            if (cards.find(c => c.id === 'music')) removeCard('music');
            if (cards.find(c => c.id === 'bilibili')) removeCard('bilibili');
        }
    }

    // Service grid click handlers
    document.querySelectorAll('.service-item').forEach(item => {
        item.addEventListener('click', () => {
            const service = item.dataset.service;

            if (service === 'music') {
                musicOpen = !musicOpen;
                handleMusicBilibili();
                return;
            }
            if (service === 'bilibili') {
                bilibiliOpen = !bilibiliOpen;
                handleMusicBilibili();
                return;
            }

            // Regular service card
            const screenshotServices = ['alipay', 'ctrip', 'news'];
            if (cards.find(c => c.id === service)) {
                removeCard(service);
            } else {
                const cls = screenshotServices.includes(service) ? 'screenshot-card' : '';
                addCard(service, 1, serviceTemplates[service], cls);
            }

            servicePanel.classList.remove('open');
            dockService.classList.remove('active');
        });
    });

    // Default: music + bilibili open
    musicOpen = true;
    bilibiliOpen = true;
    handleMusicBilibili();

    // ─── Init ────────────────────────────────────────────────
    function init() {
        scaleCanvas();
        window.addEventListener('resize', scaleCanvas);
        updateClock();
        setInterval(updateClock, 10000);
        updateLockClock();
        initADAS();
        initNav();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
