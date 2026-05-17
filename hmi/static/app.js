(function () {
    function scaleCanvas() {
        const canvas = document.getElementById('canvas');
        if (!canvas) return;
        const scale = window.innerWidth / 3840;
        canvas.style.transform = `scale(${scale})`;
    }

    // ─── Lockscreen ──────────────────────────────────────────
    const lockscreen = document.getElementById('lockscreen');
    let idleTimer = null;
    const IDLE_TIMEOUT = 900000;

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

    // AI Voice (NOVA)
    dockAi.addEventListener('click', () => {
        if (window.novaVoice) {
            window.novaVoice.toggle();
            dockAi.classList.toggle('active', window.novaVoice.isActive);
        }
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

    // ─── ADAS Three.js 3D Scene ─────────────────────────────
    let buildRoadMap = () => {};

    let adasData = {
        nearby_vehicles: [],
        nearby_pedestrians: [],
        traffic_light_state: '',
        traffic_light_distance: 0,
        lane_count: 3,
        ego_lane_index: 1,
        speed_kmh: 0,
        steer: 0,
        ego_x: 0,
        ego_y: 0,
        ego_yaw: 0,
        ego_waypoints: [],
    };

    function initADAS() {
        const canvas = document.getElementById('adas-canvas');
        if (!canvas || typeof THREE === 'undefined') return;

        const container = canvas.parentElement;
        const w = container.clientWidth || 400;
        const h = container.clientHeight || 350;

        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setSize(w, h);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;

        const scene = new THREE.Scene();
        scene.fog = new THREE.Fog(0x0a0a1a, 40, 90);

        const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 200);
        camera.position.set(0, 9, 16);
        camera.lookAt(0, 0, 0);

        // Lighting
        const ambient = new THREE.AmbientLight(0xffffff, 0.3);
        scene.add(ambient);
        const dirLight = new THREE.DirectionalLight(0xffffff, 0.6);
        dirLight.position.set(5, 20, 10);
        dirLight.castShadow = true;
        dirLight.shadow.mapSize.set(512, 512);
        scene.add(dirLight);

        // ─── Road surface ───
        const LANE_WIDTH = 3.5;
        let laneCount = 3;
        let roadGroup = new THREE.Group();
        scene.add(roadGroup);

        function buildRoad(lanes) {
            while (roadGroup.children.length) roadGroup.remove(roadGroup.children[0]);
            laneCount = lanes;
            const roadW = lanes * LANE_WIDTH;
            const roadLen = 80;

            // Asphalt
            const roadGeo = new THREE.PlaneGeometry(roadW, roadLen);
            const roadMat = new THREE.MeshStandardMaterial({ color: 0x2a2a2a, roughness: 0.9 });
            const road = new THREE.Mesh(roadGeo, roadMat);
            road.rotation.x = -Math.PI / 2;
            road.position.y = -0.01;
            road.receiveShadow = true;
            roadGroup.add(road);

            // Lane markings (dashed)
            const dashMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.5 });
            for (let i = 1; i < lanes; i++) {
                const x = -roadW / 2 + i * LANE_WIDTH;
                for (let z = -roadLen / 2; z < roadLen / 2; z += 4) {
                    const dash = new THREE.Mesh(
                        new THREE.PlaneGeometry(0.15, 2),
                        dashMat
                    );
                    dash.rotation.x = -Math.PI / 2;
                    dash.position.set(x, 0.01, z);
                    dash.userData.laneMarking = true;
                    roadGroup.add(dash);
                }
            }

            // Road edges (solid white lines)
            const edgeMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.7 });
            [-roadW / 2, roadW / 2].forEach(x => {
                const edge = new THREE.Mesh(
                    new THREE.PlaneGeometry(0.2, roadLen),
                    edgeMat
                );
                edge.rotation.x = -Math.PI / 2;
                edge.position.set(x, 0.01, 0);
                roadGroup.add(edge);
            });
        }
        buildRoad(3);

        // ─── Road geometry (static world-coord mesh, transformed per frame) ───
        const roadPathGroup = new THREE.Group();
        scene.add(roadPathGroup);
        const roadSurfaceMat = new THREE.MeshBasicMaterial({ color: 0x3a3a3a, side: THREE.DoubleSide });
        const laneDividerMat = new THREE.LineDashedMaterial({
            color: 0xffffff, dashSize: 1.5, gapSize: 1.0, linewidth: 1
        });
        const roadEdgeMat = new THREE.LineBasicMaterial({ color: 0xffffff });
        let roadMapBuilt = false;

        buildRoadMap = function(segments) {
            if (roadMapBuilt) return;
            roadMapBuilt = true;
            if (!segments || segments.length === 0) return;

            const segEdges = [];

            for (const seg of segments) {
                if (!seg || seg.length < 2) continue;
                const verts = [];
                const leftPts = [];
                const rightPts = [];
                for (const p of seg) {
                    const wx = p.x, wy = p.y;
                    const rx = p.rx || 0, ry = p.ry || 0;
                    const hw = p.hw || 1.75;
                    const lx = wx - rx * hw, ly = wy - ry * hw;
                    const rrx = wx + rx * hw, rry = wy + ry * hw;
                    verts.push(lx, 0.02, ly);
                    verts.push(rrx, 0.02, rry);
                    leftPts.push(lx, ly);
                    rightPts.push(rrx, rry);
                }
                const indices = [];
                for (let i = 0; i < seg.length - 1; i++) {
                    const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
                    indices.push(a, b, c, b, d, c);
                }
                const geo = new THREE.BufferGeometry();
                geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
                geo.setIndex(indices);
                roadPathGroup.add(new THREE.Mesh(geo, roadSurfaceMat));
                segEdges.push({ leftPts, rightPts });
            }

            // Lane dividers
            for (let i = 0; i < segEdges.length; i++) {
                const { rightPts } = segEdges[i];
                let isShared = false;
                for (let j = 0; j < segEdges.length; j++) {
                    if (i === j) continue;
                    const other = segEdges[j].leftPts;
                    if (other.length < 4 || rightPts.length < 4) continue;
                    const midIdx = Math.floor(rightPts.length / 4) * 2;
                    const dx = rightPts[midIdx] - other[midIdx];
                    const dz = rightPts[midIdx + 1] - other[midIdx + 1];
                    if (Math.abs(dx) < 1.5 && Math.abs(dz) < 1.5) {
                        isShared = true;
                        break;
                    }
                }
                const pts3d = [];
                for (let k = 0; k < rightPts.length; k += 2) {
                    pts3d.push(new THREE.Vector3(rightPts[k], 0.04, rightPts[k + 1]));
                }
                if (pts3d.length < 2) continue;
                const lineGeo = new THREE.BufferGeometry().setFromPoints(pts3d);
                if (isShared) {
                    const line = new THREE.Line(lineGeo, laneDividerMat);
                    line.computeLineDistances();
                    roadPathGroup.add(line);
                } else {
                    roadPathGroup.add(new THREE.Line(lineGeo, roadEdgeMat));
                }
            }

            // First segment left edge
            if (segEdges.length > 0) {
                const { leftPts } = segEdges[0];
                let isShared = false;
                for (let j = 1; j < segEdges.length; j++) {
                    const other = segEdges[j].rightPts;
                    if (other.length < 4 || leftPts.length < 4) continue;
                    const midIdx = Math.floor(leftPts.length / 4) * 2;
                    const dx = leftPts[midIdx] - other[midIdx];
                    const dz = leftPts[midIdx + 1] - other[midIdx + 1];
                    if (Math.abs(dx) < 1.5 && Math.abs(dz) < 1.5) {
                        isShared = true;
                        break;
                    }
                }
                if (!isShared) {
                    const pts3d = [];
                    for (let k = 0; k < leftPts.length; k += 2) {
                        pts3d.push(new THREE.Vector3(leftPts[k], 0.04, leftPts[k + 1]));
                    }
                    if (pts3d.length >= 2) {
                        const lineGeo = new THREE.BufferGeometry().setFromPoints(pts3d);
                        roadPathGroup.add(new THREE.Line(lineGeo, roadEdgeMat));
                    }
                }
            }
            console.log('[ADAS] Road map built:', segments.length, 'segments');
        };

        function updateRoadTransform(egoX, egoY, egoYaw) {
            // World coords: x=right, y=forward. Scene: x=right, z=forward (but ego faces -Z).
            // We need to rotate world so ego's forward (+Y world) aligns with scene -Z.
            // That's a base rotation of PI, plus the ego yaw offset.
            const angle = Math.PI / 2 + egoYaw;
            const cosA = Math.cos(angle);
            const sinA = Math.sin(angle);
            // group transform: point' = R(angle) * point + position
            // We want: scenePos = R(angle) * worldPos + offset  such that ego maps to (0,0,8)
            // (0,0,8) = R(angle) * (egoX, 0, egoY) + offset
            // offset = (0,0,8) - R(angle) * (egoX, 0, egoY)
            const rx = cosA * egoX + sinA * egoY;
            const rz = -sinA * egoX + cosA * egoY;
            roadPathGroup.rotation.y = angle;
            roadPathGroup.position.set(-rx, 0, -rz + 8);
        }

        // ─── Ego vehicle (white luxury sports car) ───
        const egoGroup = new THREE.Group();
        const egoMat = new THREE.MeshStandardMaterial({ color: 0xf0f0f0, metalness: 0.7, roughness: 0.2 });
        // Body (sleek low profile)
        const egoBody = new THREE.Mesh(
            new THREE.BoxGeometry(1.9, 0.5, 4.5),
            egoMat
        );
        egoBody.position.y = 0.45;
        egoBody.castShadow = true;
        egoGroup.add(egoBody);
        // Hood slope
        const egoHood = new THREE.Mesh(
            new THREE.BoxGeometry(1.7, 0.15, 1.4),
            egoMat
        );
        egoHood.position.set(0, 0.78, -1.2);
        egoGroup.add(egoHood);
        // Cabin (tinted glass)
        const egoCabin = new THREE.Mesh(
            new THREE.BoxGeometry(1.5, 0.45, 1.8),
            new THREE.MeshStandardMaterial({ color: 0x1a1a2e, metalness: 0.5, roughness: 0.1 })
        );
        egoCabin.position.set(0, 0.92, 0.1);
        egoGroup.add(egoCabin);
        // Rear spoiler
        const egoSpoiler = new THREE.Mesh(
            new THREE.BoxGeometry(1.6, 0.06, 0.3),
            egoMat
        );
        egoSpoiler.position.set(0, 0.85, 2.1);
        egoGroup.add(egoSpoiler);
        // Wheels
        const wheelGeo = new THREE.CylinderGeometry(0.32, 0.32, 0.22, 16);
        const wheelMat = new THREE.MeshStandardMaterial({ color: 0x111111 });
        const rimMat = new THREE.MeshStandardMaterial({ color: 0xcccccc, metalness: 0.8 });
        [[-0.9, 0.32, 1.3], [0.9, 0.32, 1.3], [-0.9, 0.32, -1.3], [0.9, 0.32, -1.3]].forEach(p => {
            const wheel = new THREE.Mesh(wheelGeo, wheelMat);
            wheel.rotation.z = Math.PI / 2;
            wheel.position.set(...p);
            egoGroup.add(wheel);
            const rim = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.18, 0.23, 8), rimMat);
            rim.rotation.z = Math.PI / 2;
            rim.position.set(...p);
            egoGroup.add(rim);
        });
        // Headlights (LED strip look)
        const hlMat = new THREE.MeshBasicMaterial({ color: 0xffffff });
        [[-0.7, 0.5, -2.25], [0.7, 0.5, -2.25]].forEach(p => {
            const hl = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.08, 0.05), hlMat);
            hl.position.set(...p);
            egoGroup.add(hl);
        });
        // Taillights (wide LED bar)
        const tlMat = new THREE.MeshBasicMaterial({ color: 0xff2020 });
        const tailBar = new THREE.Mesh(
            new THREE.BoxGeometry(1.4, 0.06, 0.05),
            tlMat
        );
        tailBar.position.set(0, 0.55, 2.25);
        egoGroup.add(tailBar);
        // Pulse rings (radar ripple effect)
        const pulseMat = new THREE.MeshBasicMaterial({ color: 0x4DD8E5, transparent: true, opacity: 0.6, side: THREE.DoubleSide });
        const pulseMat2 = new THREE.MeshBasicMaterial({ color: 0x4DD8E5, transparent: true, opacity: 0.35, side: THREE.DoubleSide });
        const pulseRing = new THREE.Mesh(new THREE.RingGeometry(1.4, 1.7, 32), pulseMat);
        pulseRing.rotation.x = -Math.PI / 2;
        pulseRing.position.y = 0.05;
        egoGroup.add(pulseRing);
        const pulseRing2 = new THREE.Mesh(new THREE.RingGeometry(2.2, 2.4, 32), pulseMat2);
        pulseRing2.rotation.x = -Math.PI / 2;
        pulseRing2.position.y = 0.05;
        egoGroup.add(pulseRing2);

        egoGroup.position.set(0, 0, 8);
        scene.add(egoGroup);

        // ─── Ego waypoint path (wide translucent strip) ───
        const wpGroup = new THREE.Group();
        scene.add(wpGroup);
        const wpMat = new THREE.MeshBasicMaterial({
            color: 0x00ccff, transparent: true, opacity: 0.35, side: THREE.DoubleSide
        });
        function updateWaypoints(wps) {
            while (wpGroup.children.length) {
                const c = wpGroup.children[0];
                if (c.geometry) c.geometry.dispose();
                wpGroup.remove(c);
            }
            if (!wps || wps.length < 2) return;
            const halfW = 0.9;
            const verts = [];
            for (const p of wps) {
                const px = -p.x, pz = -p.z + 8;
                verts.push(px - halfW, 0.06, pz);
                verts.push(px + halfW, 0.06, pz);
            }
            const indices = [];
            for (let i = 0; i < wps.length - 1; i++) {
                const a = i * 2, b = i * 2 + 1, c = (i + 1) * 2, d = (i + 1) * 2 + 1;
                indices.push(a, b, c, b, d, c);
            }
            const geo = new THREE.BufferGeometry();
            geo.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
            geo.setIndex(indices);
            wpGroup.add(new THREE.Mesh(geo, wpMat));
        }

        // ─── NPC vehicles pool (ID-stable, dynamic size) ───
        const vehiclePool = [];
        const VEHICLE_POOL_SIZE = 15;
        const NPC_COLORS = [0xf5a623, 0xe55b3c, 0x5b8def, 0x8855cc, 0xcccccc, 0x444444, 0xaa0000];
        function createNPCVehicle(colorIdx) {
            const group = new THREE.Group();
            const color = NPC_COLORS[colorIdx % NPC_COLORS.length];
            const darkerColor = new THREE.Color(color).multiplyScalar(0.7).getHex();
            // Body (default 1.8 x 0.6 x 4.0, will be scaled per-vehicle)
            const body = new THREE.Mesh(
                new THREE.BoxGeometry(1, 0.6, 1),
                new THREE.MeshStandardMaterial({ color, metalness: 0.3, roughness: 0.4 })
            );
            body.position.y = 0.47;
            body.castShadow = true;
            body.name = 'body';
            group.add(body);
            // Cabin
            const cabin = new THREE.Mesh(
                new THREE.BoxGeometry(0.8, 0.45, 0.5),
                new THREE.MeshStandardMaterial({ color: darkerColor, metalness: 0.2, roughness: 0.5 })
            );
            cabin.position.set(0, 0.95, 0);
            cabin.name = 'cabin';
            group.add(cabin);
            // Wheels (positioned dynamically)
            const whs = [];
            for (let i = 0; i < 4; i++) {
                const wh = new THREE.Mesh(wheelGeo, wheelMat);
                wh.rotation.z = Math.PI / 2;
                group.add(wh);
                whs.push(wh);
            }
            // Headlights
            const hls = [];
            [0, 1].forEach(() => {
                const hl = new THREE.Mesh(new THREE.SphereGeometry(0.08, 6, 6), hlMat);
                group.add(hl);
                hls.push(hl);
            });
            // Taillights
            const tls = [];
            [0, 1].forEach(() => {
                const tl2 = new THREE.Mesh(new THREE.SphereGeometry(0.08, 6, 6), tlMat);
                group.add(tl2);
                tls.push(tl2);
            });
            group.visible = false;
            scene.add(group);
            return { group, body, cabin, whs, hls, tls,
                targetX: 0, targetZ: 0, currentX: 0, currentZ: 0,
                targetHeading: 0, currentHeading: 0, assignedId: null,
                sizeW: 1.8, sizeL: 4.0, sizeH: 1.5, vtype: 'car' };
        }
        for (let i = 0; i < VEHICLE_POOL_SIZE; i++) vehiclePool.push(createNPCVehicle(i));

        function resizeVehicleSlot(slot, w, l, h, vtype) {
            const typeChanged = slot.vtype !== vtype;
            if (!typeChanged && Math.abs(slot.sizeW - w) < 0.1 && Math.abs(slot.sizeL - l) < 0.1) return;
            slot.sizeW = w; slot.sizeL = l; slot.sizeH = h; slot.vtype = vtype;

            if (vtype === 'bike') {
                // Rider on bicycle / e-bike / motorcycle
                slot.body.scale.set(0.4, 1.6, 0.9);
                slot.body.position.y = 1.0;
                slot.cabin.scale.set(0.35, 0.6, 0.35);
                slot.cabin.position.set(0, 1.9, 0);
                slot.whs[0].position.set(0, 0.28, -0.6);
                slot.whs[1].position.set(0, 0.28, 0.6);
                slot.whs[2].position.set(0, -10, 0);
                slot.whs[3].position.set(0, -10, 0);
                slot.hls[0].position.set(0, 0.7, -0.9);
                slot.hls[1].position.set(0, -10, 0);
                slot.tls[0].position.set(0, 0.7, 0.9);
                slot.tls[1].position.set(0, -10, 0);
            } else {
                const hw = w / 2, hl = l / 2;
                slot.body.scale.set(w, 1, l);
                slot.body.position.y = 0.47;
                slot.cabin.scale.set(w * 0.75, 1, l * 0.45);
                slot.cabin.position.set(0, 0.95, -l * 0.05);
                const wz = hl * 0.6, wx = hw * 0.9;
                slot.whs[0].position.set(-wx, 0.25, wz);
                slot.whs[1].position.set(wx, 0.25, wz);
                slot.whs[2].position.set(-wx, 0.25, -wz);
                slot.whs[3].position.set(wx, 0.25, -wz);
                slot.hls[0].position.set(-hw * 0.6, 0.45, -hl);
                slot.hls[1].position.set(hw * 0.6, 0.45, -hl);
                slot.tls[0].position.set(-hw * 0.6, 0.45, hl);
                slot.tls[1].position.set(hw * 0.6, 0.45, hl);
            }
        }

        // ─── Pedestrian pool ───
        const pedestrianPool = [];
        const PED_POOL_SIZE = 10;
        function createPedestrian() {
            const group = new THREE.Group();
            const skinColor = 0xf0c8a0;
            const clothColor = 0x3355aa;
            // Torso
            const torso = new THREE.Mesh(
                new THREE.BoxGeometry(0.4, 0.6, 0.25),
                new THREE.MeshStandardMaterial({ color: clothColor })
            );
            torso.position.y = 1.1;
            group.add(torso);
            // Head
            const head = new THREE.Mesh(
                new THREE.SphereGeometry(0.15, 8, 8),
                new THREE.MeshStandardMaterial({ color: skinColor })
            );
            head.position.y = 1.6;
            group.add(head);
            // Legs
            const legGeo = new THREE.BoxGeometry(0.14, 0.55, 0.14);
            const legMat = new THREE.MeshStandardMaterial({ color: 0x333344 });
            const legL = new THREE.Mesh(legGeo, legMat);
            legL.position.set(-0.1, 0.5, 0);
            group.add(legL);
            const legR = new THREE.Mesh(legGeo, legMat);
            legR.position.set(0.1, 0.5, 0);
            group.add(legR);
            // Arms
            const armGeo = new THREE.BoxGeometry(0.12, 0.5, 0.12);
            const armMat = new THREE.MeshStandardMaterial({ color: skinColor });
            const armL = new THREE.Mesh(armGeo, armMat);
            armL.position.set(-0.3, 1.1, 0);
            group.add(armL);
            const armR = new THREE.Mesh(armGeo, armMat);
            armR.position.set(0.3, 1.1, 0);
            group.add(armR);
            group.userData.legL = legL;
            group.userData.legR = legR;
            group.userData.armL = armL;
            group.userData.armR = armR;
            group.visible = false;
            scene.add(group);
            return { group, targetX: 0, targetZ: 0, currentX: 0, currentZ: 0, crossing: false, assignedId: null };
        }
        for (let i = 0; i < PED_POOL_SIZE; i++) pedestrianPool.push(createPedestrian());

        // ─── Traffic light indicator (right side, large) ───
        const tlGroup = new THREE.Group();
        const tlHousing = new THREE.Mesh(
            new THREE.BoxGeometry(1.6, 4.5, 0.7),
            new THREE.MeshStandardMaterial({ color: 0x1a1a1a })
        );
        tlGroup.add(tlHousing);
        const tlLights = {};
        const lightColors = { Red: 0xff0000, Yellow: 0xffcc00, Green: 0x00ff66 };
        let yOff = 1.5;
        ['Red', 'Yellow', 'Green'].forEach(name => {
            const light = new THREE.Mesh(
                new THREE.SphereGeometry(0.55, 16, 16),
                new THREE.MeshBasicMaterial({ color: lightColors[name], transparent: true, opacity: 0.15 })
            );
            light.position.set(0, yOff, 0.36);
            tlGroup.add(light);
            tlLights[name] = light;
            yOff -= 1.5;
        });
        tlGroup.position.set(16, 5, 5);
        tlGroup.visible = false;
        scene.add(tlGroup);

        // ─── Animation loop ───
        let lastW = w, lastH = h;
        let frame = 0;
        const LERP = 0.08;

        function animate() {
            if (!document.getElementById('adas-canvas')) return;
            frame++;

            // Resize check
            const cw = container.clientWidth;
            const ch = container.clientHeight;
            if (cw !== lastW || ch !== lastH) {
                lastW = cw; lastH = ch;
                renderer.setSize(cw, ch);
                camera.aspect = cw / ch;
                camera.updateProjectionMatrix();
            }

            // Update road transform based on ego world pose
            if (roadMapBuilt) {
                roadGroup.visible = false;
                updateRoadTransform(adasData.ego_x, adasData.ego_y, adasData.ego_yaw);
            } else {
                roadGroup.visible = true;
                if (adasData.lane_count !== laneCount && adasData.lane_count >= 1) {
                    buildRoad(adasData.lane_count);
                }
                // Lane marking flow animation (only when static road visible)
                const flowSpeed = adasData.speed_kmh * 0.005;
                roadGroup.children.forEach(child => {
                    if (child.userData.laneMarking) {
                        child.position.z += flowSpeed;
                        if (child.position.z > 40) child.position.z -= 80;
                    }
                });
            }

            // Ego waypoint path
            if (frame % 5 === 0) updateWaypoints(adasData.ego_waypoints);

            // Ego pulse ring
            pulseMat.opacity = 0.4 + 0.25 * Math.sin(frame * 0.06);
            pulseRing.scale.setScalar(1 + 0.15 * Math.sin(frame * 0.04));
            pulseMat2.opacity = 0.2 + 0.15 * Math.sin(frame * 0.04 + 1.5);
            pulseRing2.scale.setScalar(1 + 0.1 * Math.sin(frame * 0.03 + 1.0));

            // Position ego in correct lane
            const roadW = laneCount * LANE_WIDTH;
            const egoLaneX = -roadW / 2 + (adasData.ego_lane_index + 0.5) * LANE_WIDTH;
            egoGroup.position.x += (egoLaneX - egoGroup.position.x) * 0.05;

            // Update NPC vehicles with stable ID assignment + lerp
            const activeIds = new Set();
            for (const v of adasData.nearby_vehicles) {
                const vid = v.id != null ? v.id : `idx_${adasData.nearby_vehicles.indexOf(v)}`;
                activeIds.add(vid);
                let slot = null;
                let isNew = false;
                for (const p of vehiclePool) {
                    if (p.assignedId === vid) { slot = p; break; }
                }
                if (!slot) {
                    for (const p of vehiclePool) {
                        if (!p.assignedId) { slot = p; isNew = true; break; }
                    }
                }
                if (!slot) continue;
                slot.assignedId = vid;
                slot.targetX = -v.x;
                slot.targetZ = -v.z + 8;
                slot.targetHeading = -(v.heading || 0);
                if (v.w && v.l) resizeVehicleSlot(slot, v.w, v.l, v.h || 1.5, v.type || 'car');
                if (isNew) {
                    slot.currentX = slot.targetX;
                    slot.currentZ = slot.targetZ;
                    slot.currentHeading = slot.targetHeading;
                    slot.group.position.set(slot.currentX, 0, slot.currentZ);
                }
                slot.group.visible = true;
            }
            for (const pool of vehiclePool) {
                if (pool.assignedId && !activeIds.has(pool.assignedId)) {
                    pool.assignedId = null;
                    pool.group.visible = false;
                }
                if (pool.group.visible) {
                    pool.currentX += (pool.targetX - pool.currentX) * LERP;
                    pool.currentZ += (pool.targetZ - pool.currentZ) * LERP;
                    pool.currentHeading += (pool.targetHeading - pool.currentHeading) * LERP;
                    pool.group.position.set(pool.currentX, 0, pool.currentZ);
                    pool.group.rotation.y = THREE.MathUtils.degToRad(pool.currentHeading);
                }
            }

            // Update pedestrians with stable ID + lerp + walk animation
            const activePedIds = new Set();
            for (const p of adasData.nearby_pedestrians) {
                const pid = p.id != null ? p.id : `pidx_${adasData.nearby_pedestrians.indexOf(p)}`;
                activePedIds.add(pid);
                let slot = null;
                let isNewPed = false;
                for (const ped of pedestrianPool) {
                    if (ped.assignedId === pid) { slot = ped; break; }
                }
                if (!slot) {
                    for (const ped of pedestrianPool) {
                        if (!ped.assignedId) { slot = ped; isNewPed = true; break; }
                    }
                }
                if (!slot) continue;
                slot.assignedId = pid;
                slot.targetX = -p.x;  // 镜像修正
                slot.targetZ = -p.z + 8;
                slot.crossing = p.crossing;
                if (isNewPed) {
                    slot.currentX = slot.targetX;
                    slot.currentZ = slot.targetZ;
                    slot.group.position.set(slot.currentX, 0, slot.currentZ);
                }
                slot.group.visible = true;
            }
            for (const ped of pedestrianPool) {
                if (ped.assignedId && !activePedIds.has(ped.assignedId)) {
                    ped.assignedId = null;
                    ped.group.visible = false;
                }
                if (ped.group.visible) {
                    ped.currentX += (ped.targetX - ped.currentX) * LERP;
                    ped.currentZ += (ped.targetZ - ped.currentZ) * LERP;
                    ped.group.position.set(ped.currentX, 0, ped.currentZ);
                    const swing = Math.sin(frame * 0.12) * 0.3;
                    ped.group.userData.legL.rotation.x = swing;
                    ped.group.userData.legR.rotation.x = -swing;
                    ped.group.userData.armL.rotation.x = -swing;
                    ped.group.userData.armR.rotation.x = swing;
                    const torso = ped.group.children[0];
                    if (ped.crossing) {
                        torso.material.color.setHex(0xcc2222);
                    } else {
                        torso.material.color.setHex(0x3355aa);
                    }
                }
            }

            // Traffic light
            const tlState = adasData.traffic_light_state;
            if (tlState && (tlState === 'Red' || tlState === 'Yellow' || tlState === 'Green')) {
                tlGroup.visible = true;
                tlGroup.lookAt(camera.position);
                Object.entries(tlLights).forEach(([name, mesh]) => {
                    mesh.material.opacity = (name === tlState) ? 1.0 : 0.15;
                });
            } else {
                tlGroup.visible = false;
            }

            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();
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

    const biliVideos = [
        { poster: '/static/media/Huntrix.jpg', bvid: 'BV1oeNXzBEK6' },
        { poster: '/static/media/Interstellar.jpg', bvid: 'BV19A411q7sB' },
        { poster: '/static/media/Faerwell My Concubine.jpg', bvid: 'BV1wF411S71j' },
        { poster: '/static/media/The Devil wears Prrada.jpg', bvid: 'BV1dzHzzyERq' },
        { poster: '/static/media/Nghesieu DE.jpg', bvid: 'BV15czjBNEn6' },
    ];

    const bilibiliHTML = `
        <div class="bilibili-inner">
            <span class="bilibili-label">Bilibili: Recommend</span>
            <div class="bilibili-scroll">
                ${biliVideos.map(v => `<button class="bili-poster-btn" type="button" onclick="window.openBiliPlayer('${v.bvid}')"><img class="bili-poster" src="${v.poster}" draggable="false"></button>`).join('')}
            </div>
        </div>`;

    const serviceTemplates = {
        alipay: `<img class="service-card-img" src="/static/media/alipay.jpg" alt="Alipay">`,
        ctrip: `<img class="service-card-img" src="/static/media/Ctrip.png" alt="Ctrip">`,
        news: `<img class="service-card-img" src="/static/media/News.png" alt="News">`,
        parking: `<div class="three-card">
            <canvas class="three-canvas" id="parking-3d"></canvas>
            <div class="three-overlay">
                <span class="three-title">Smart Parking</span>
                <span class="three-sub">B2 · 12 Available</span>
            </div>
        </div>`,
        charging: `<div class="three-card">
            <canvas class="three-canvas" id="charging-3d"></canvas>
            <div class="three-overlay">
                <span class="three-title">Charging</span>
                <span class="three-sub">3 Nearby · 0.8 km</span>
            </div>
        </div>`,
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
        if (id === 'bili-player') {
            // Restore music + bilibili after closing player
            setTimeout(() => {
                musicOpen = true;
                bilibiliOpen = true;
                handleMusicBilibili();
                if (_wasPlayingBeforeBili) {
                    audio.volume = 0;
                    audio.play();
                    isPlaying = true;
                    const btn = document.getElementById('btn-play');
                    if (btn) btn.textContent = '⏸';
                    let vol = 0;
                    const fadeIn = setInterval(() => {
                        vol += 0.05;
                        if (vol >= 1) { audio.volume = 1; clearInterval(fadeIn); }
                        else { audio.volume = vol; }
                    }, 50);
                }
            }, 400);
        }
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

        // Init Three.js scenes if present
        if (id === 'parking') setTimeout(() => initParking3D(), 100);
        if (id === 'charging') setTimeout(() => initCharging3D(), 100);

        rebindPlayerButtons();
    }

    function upsertCard(id, slots, innerHTML, extraClass) {
        const existing = cards.find(c => c.id === id);
        if (existing) {
            existing.element.innerHTML = `<button class="card-close">✕</button>` + innerHTML;
            existing.element.classList.add('fc-pulse');
            setTimeout(() => existing.element.classList.remove('fc-pulse'), 650);
            existing.element.querySelector('.card-close').addEventListener('click', () => removeCard(id));
            if (id === 'parking') setTimeout(() => initParking3D(), 100);
            if (id === 'charging') setTimeout(() => initCharging3D(), 100);
            rebindPlayerButtons();
            return;
        }
        addCard(id, slots, innerHTML, extraClass);
    }

    function fcStatusCard(title, value, meta) {
        return `<div class="fc-status-card">
            <span class="fc-kicker">NOVA EXECUTED</span>
            <span class="fc-title">${title}</span>
            <span class="fc-value">${value}</span>
            <span class="fc-meta">${meta || ''}</span>
        </div>`;
    }

    function normalizeServiceName(service) {
        const map = {
            '奶茶': 'alipay',
            '点奶茶': 'alipay',
            '支付': 'alipay',
            '支付宝': 'alipay',
            '机票': 'ctrip',
            '航班': 'ctrip',
            '携程': 'ctrip',
            '新闻': 'news',
            '停车': 'parking',
            '停车场': 'parking',
            '充电': 'charging',
            '音乐': 'music',
            '视频': 'bilibili',
        };
        return map[service] || service || '';
    }

    function showActionResult(action, title, value, meta) {
        upsertCard('fc-' + action, 1, fcStatusCard(title, value, meta), 'fc-card');
    }

    function normalizeActionItem(item) {
        if (!item) return null;
        const action = item.action || item.function || item.name;
        const params = item.params || item.parameters || {};
        if (!action) return null;
        return { action, params };
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
        bindPosterClicks();
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

    // Default: music open, bilibili via select panel
    musicOpen = true;
    bilibiliOpen = true;
    handleMusicBilibili();

    // ─── Bilibili Poster Click → iframe Player ───────────────
    function bindPosterClicks() {}

    let _wasPlayingBeforeBili = false;

    function openBiliPlayer(bvid) {
        console.log('[Bili] Opening player for:', bvid);
        _wasPlayingBeforeBili = isPlaying;
        if (isPlaying) { audio.pause(); isPlaying = false; }
        const allIds = cards.map(c => c.id);
        allIds.forEach(id => removeCard(id));

        setTimeout(() => {
            const playerHTML = `
                <div class="bili-player-inner">
                    <iframe class="bili-iframe"
                        src="https://player.bilibili.com/player.html?bvid=${bvid}&page=1&high_quality=1&danmaku=0&autoplay=1"
                        allowfullscreen="true"
                        allow="autoplay; encrypted-media"
                        frameborder="0"
                        scrolling="no">
                    </iframe>
                </div>`;
            addCard('bili-player', 4, playerHTML, 'bili-player-card');
        }, 800);
    }
    window.openBiliPlayer = openBiliPlayer;

    // ─── Three.js: Parking 3D ──────────────────────────────────
    function initParking3D() {
        const canvas = document.getElementById('parking-3d');
        if (!canvas || typeof THREE === 'undefined') return;

        const container = canvas.parentElement;
        const w = container.clientWidth || 300;
        const h = container.clientHeight || 400;

        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setSize(w, h);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
        camera.position.set(0, 8, 6);
        camera.lookAt(0, 0, 0);

        // Ambient + directional light
        scene.add(new THREE.AmbientLight(0xffffff, 0.4));
        const dirLight = new THREE.DirectionalLight(0x4DD8E5, 0.8);
        dirLight.position.set(3, 8, 4);
        scene.add(dirLight);

        // Ground plane
        const ground = new THREE.Mesh(
            new THREE.PlaneGeometry(10, 8),
            new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0.9 })
        );
        ground.rotation.x = -Math.PI / 2;
        scene.add(ground);

        // Parking slots (2 rows x 4 cols)
        const slots = [
            { x: -3, z: -1.5, free: true }, { x: -1, z: -1.5, free: false },
            { x: 1, z: -1.5, free: true, recommend: true }, { x: 3, z: -1.5, free: false },
            { x: -3, z: 1.5, free: true }, { x: -1, z: 1.5, free: true },
            { x: 1, z: 1.5, free: false }, { x: 3, z: 1.5, free: true },
        ];

        slots.forEach(s => {
            // Slot outline
            const color = s.recommend ? 0x4DD8E5 : s.free ? 0x4DDB8F : 0xff3b30;
            const slotGeo = new THREE.BoxGeometry(1.6, 0.05, 2.2);
            const slotMat = new THREE.MeshStandardMaterial({
                color, transparent: true, opacity: s.recommend ? 0.5 : 0.25
            });
            const slotMesh = new THREE.Mesh(slotGeo, slotMat);
            slotMesh.position.set(s.x, 0.03, s.z);
            scene.add(slotMesh);

            // Parked car (small box) for occupied
            if (!s.free) {
                const car = new THREE.Mesh(
                    new THREE.BoxGeometry(1.0, 0.5, 1.8),
                    new THREE.MeshStandardMaterial({ color: 0x555555, roughness: 0.6 })
                );
                car.position.set(s.x, 0.3, s.z);
                scene.add(car);
            }

            // Glow ring for recommended
            if (s.recommend) {
                const ring = new THREE.Mesh(
                    new THREE.RingGeometry(0.9, 1.0, 32),
                    new THREE.MeshBasicMaterial({ color: 0x4DD8E5, transparent: true, opacity: 0.6, side: THREE.DoubleSide })
                );
                ring.rotation.x = -Math.PI / 2;
                ring.position.set(s.x, 0.06, s.z);
                ring.userData.pulse = true;
                scene.add(ring);
            }
        });

        // Lane markings
        const laneMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.15 });
        const lane = new THREE.Mesh(new THREE.PlaneGeometry(10, 0.08), laneMat);
        lane.rotation.x = -Math.PI / 2;
        lane.position.y = 0.02;
        scene.add(lane);

        let frame = 0;
        let lastW = w, lastH = h;
        function animate() {
            if (!document.getElementById('parking-3d')) return;
            frame++;

            const cw = container.clientWidth;
            const ch = container.clientHeight;
            if (cw !== lastW || ch !== lastH) {
                lastW = cw; lastH = ch;
                renderer.setSize(cw, ch);
                camera.aspect = cw / ch;
                camera.updateProjectionMatrix();
            }

            scene.traverse(obj => {
                if (obj.userData.pulse) {
                    obj.material.opacity = 0.4 + 0.3 * Math.sin(frame * 0.05);
                }
            });
            camera.position.x = Math.sin(frame * 0.003) * 0.5;
            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();
    }

    // ─── Three.js: Charging 3D ──────────────────────────────────
    function initCharging3D() {
        const canvas = document.getElementById('charging-3d');
        if (!canvas || typeof THREE === 'undefined') return;

        const container = canvas.parentElement;
        const w = container.clientWidth || 300;
        const h = container.clientHeight || 400;

        const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
        renderer.setSize(w, h);
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));

        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 100);
        camera.position.set(0, 3, 6);
        camera.lookAt(0, 1.2, 0);

        scene.add(new THREE.AmbientLight(0xffffff, 0.3));
        const pointLight = new THREE.PointLight(0x4DDB8F, 1.5, 10);
        pointLight.position.set(0, 4, 2);
        scene.add(pointLight);

        // Ground
        const ground = new THREE.Mesh(
            new THREE.PlaneGeometry(8, 6),
            new THREE.MeshStandardMaterial({ color: 0x1a1a2e, roughness: 0.9 })
        );
        ground.rotation.x = -Math.PI / 2;
        scene.add(ground);

        // Charging pillar
        const pillar = new THREE.Mesh(
            new THREE.BoxGeometry(0.6, 2.5, 0.4),
            new THREE.MeshStandardMaterial({ color: 0x2a2a3e, roughness: 0.5 })
        );
        pillar.position.set(0, 1.25, 0);
        scene.add(pillar);

        // Screen on pillar
        const screen = new THREE.Mesh(
            new THREE.PlaneGeometry(0.4, 0.6),
            new THREE.MeshBasicMaterial({ color: 0x4DDB8F, transparent: true, opacity: 0.8 })
        );
        screen.position.set(0, 1.8, 0.21);
        scene.add(screen);

        // Charging cable (curved tube)
        const curve = new THREE.CatmullRomCurve3([
            new THREE.Vector3(0.3, 1.0, 0.2),
            new THREE.Vector3(0.8, 0.6, 0.5),
            new THREE.Vector3(1.5, 0.3, 0.3),
            new THREE.Vector3(2.0, 0.3, 0),
        ]);
        const tube = new THREE.Mesh(
            new THREE.TubeGeometry(curve, 20, 0.05, 8, false),
            new THREE.MeshStandardMaterial({ color: 0x333333, roughness: 0.4 })
        );
        scene.add(tube);

        // Car body (simplified)
        const carBody = new THREE.Mesh(
            new THREE.BoxGeometry(1.8, 0.6, 1.0),
            new THREE.MeshStandardMaterial({ color: 0x3a3a5e, roughness: 0.4, metalness: 0.3 })
        );
        carBody.position.set(2.0, 0.4, 0);
        scene.add(carBody);
        const carTop = new THREE.Mesh(
            new THREE.BoxGeometry(1.0, 0.4, 0.8),
            new THREE.MeshStandardMaterial({ color: 0x3a3a5e, roughness: 0.4, metalness: 0.3 })
        );
        carTop.position.set(2.0, 0.8, 0);
        scene.add(carTop);

        // Energy particles
        const particleCount = 30;
        const particleGeo = new THREE.BufferGeometry();
        const positions = new Float32Array(particleCount * 3);
        for (let i = 0; i < particleCount; i++) {
            positions[i * 3] = (Math.random() - 0.5) * 2;
            positions[i * 3 + 1] = Math.random() * 3;
            positions[i * 3 + 2] = (Math.random() - 0.5) * 2;
        }
        particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        const particles = new THREE.Points(particleGeo, new THREE.PointsMaterial({
            color: 0x4DDB8F, size: 0.06, transparent: true, opacity: 0.7
        }));
        scene.add(particles);

        let frame = 0;
        let lastW = w, lastH = h;
        function animate() {
            if (!document.getElementById('charging-3d')) return;
            frame++;

            const cw = container.clientWidth;
            const ch = container.clientHeight;
            if (cw !== lastW || ch !== lastH) {
                lastW = cw; lastH = ch;
                renderer.setSize(cw, ch);
                camera.aspect = cw / ch;
                camera.updateProjectionMatrix();
            }

            screen.material.opacity = 0.5 + 0.3 * Math.sin(frame * 0.08);

            const pos = particles.geometry.attributes.position.array;
            for (let i = 0; i < particleCount; i++) {
                pos[i * 3 + 1] += 0.015;
                if (pos[i * 3 + 1] > 3) pos[i * 3 + 1] = 0;
            }
            particles.geometry.attributes.position.needsUpdate = true;

            camera.position.x = Math.sin(frame * 0.004) * 0.3;
            pointLight.intensity = 1.2 + 0.3 * Math.sin(frame * 0.06);

            renderer.render(scene, camera);
            requestAnimationFrame(animate);
        }
        animate();
    }

    // ─── WebSocket 实时通信 ─────────────────────────────────
    function initWebSocket() {
        const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${location.host}/ws`;
        let ws = null;
        let reconnectTimer = null;

        function connect() {
            ws = new WebSocket(wsUrl);
            ws.onopen = () => console.log('[WS] Connected');
            ws.onclose = () => {
                console.log('[WS] Disconnected, reconnecting...');
                reconnectTimer = setTimeout(connect, 2000);
            };
            ws.onerror = () => ws.close();
            ws.onmessage = (evt) => {
                try {
                    const msg = JSON.parse(evt.data);
                    if (msg.type === 'road_map' && msg.segments) {
                        buildRoadMap(msg.segments);
                    } else if (msg.type === 'state_update' && msg.vehicle) {
                        const v = msg.vehicle;
                        adasData.speed_kmh = v.speed_kmh || 0;
                        adasData.steer = v.steer || 0;
                        adasData.nearby_vehicles = v.nearby_vehicles || [];
                        adasData.nearby_pedestrians = v.nearby_pedestrians || [];
                        adasData.traffic_light_state = v.traffic_light_state || '';
                        adasData.traffic_light_distance = v.traffic_light_distance || 0;
                        adasData.lane_count = v.lane_count || 3;
                        adasData.ego_lane_index = v.ego_lane_index || 1;
                        adasData.ego_x = v.location_x || 0;
                        adasData.ego_y = v.location_y || 0;
                        adasData.ego_yaw = (v.rotation_yaw || 0) * Math.PI / 180;
                        adasData.ego_waypoints = v.ego_waypoints || [];

                        // Update speed card + drive indicators
                        const speedEl = document.getElementById('speed-number');
                        const mainSpeedEl = document.getElementById('main-speed');
                        if (speedEl) speedEl.textContent = Math.round(v.speed_kmh);
                        if (mainSpeedEl) mainSpeedEl.textContent = Math.round(v.speed_kmh) + ' km/h';

                        const throttleFill = document.getElementById('throttle-fill');
                        const brakeFill = document.getElementById('brake-fill');
                        const steerVal = document.getElementById('steer-value');
                        const gearEl = document.getElementById('gear-indicator');
                        if (throttleFill) throttleFill.style.width = Math.round((v.throttle || 0) * 100) + '%';
                        if (brakeFill) brakeFill.style.width = Math.round((v.brake || 0) * 100) + '%';
                        if (steerVal) steerVal.textContent = Math.round(v.wheel_angle_deg || 0) + '°';
                        if (gearEl) {
                            if (v.is_reverse) gearEl.textContent = 'R';
                            else if (v.gear === 0) gearEl.textContent = 'P';
                            else gearEl.textContent = 'D';
                        }
                    }
                    // Forward FC messages to NOVA voice handler
                    if ((msg.type === 'fc_pending' || msg.type === 'fc_executed') && window._novaHandleFCMessage) {
                        window._novaHandleFCMessage(msg);
                    }
                    // Execute HMI actions from Function Calling
                    if (msg.type === 'fc_executed' && msg.function) {
                        _executeFCAction(msg.function, msg.params || {});
                    }
                } catch (e) {}
            };
        }
        connect();
    }

    // ─── FC Action Executor ─────────────────────────────────
    function _executeFCAction(funcName, params) {
        console.log('[FC] Executing HMI action:', funcName, params);
        switch (funcName) {
            case 'proactive_service_plan': {
                const intent = params.intent || 'Proactive Service';
                const rawConfidence = Number(params.confidence);
                const confidence = params.confidence !== undefined
                    ? Math.round(rawConfidence <= 1 ? rawConfidence * 100 : rawConfidence)
                    : null;
                const reason = params.reason || params.hmi_feedback || '已识别用户需求并生成服务计划';
                const actions = Array.isArray(params.actions) ? params.actions : [];
                const planHtml = `<div class="fc-status-card">
                    <span class="fc-kicker">INTENT UNDERSTANDING</span>
                    <span class="fc-title">${intent}</span>
                    <span class="fc-value">${confidence !== null && !Number.isNaN(confidence) ? confidence + '%' : 'PLAN'}</span>
                    <span class="fc-meta">${reason}</span>
                </div>`;
                upsertCard('fc-intent', 1, planHtml, 'fc-card');
                actions.map(normalizeActionItem).filter(Boolean).forEach(item => {
                    _executeFCAction(item.action, item.params);
                });
                break;
            }
            case 'set_ac_temperature': {
                const temp = params.temperature ?? params.temp ?? 22;
                showActionResult('ac', 'Climate', `${temp}°C`, '空调温度已调整');
                document.documentElement.style.setProperty('--accent-cyan', temp <= 22 ? '#3bd5ff' : '#ff9500');
                break;
            }
            case 'set_seat_ventilation': {
                const on = params.on !== false;
                showActionResult('seat', 'Seat Ventilation', on ? 'ON' : 'OFF', on ? '座椅通风已开启' : '座椅通风已关闭');
                break;
            }
            case 'toggle_window': {
                const open = params.open !== false;
                showActionResult('window', 'Window', open ? 'OPEN' : 'CLOSED', open ? '车窗已打开' : '车窗已关闭');
                if (window.HMI && open) window.HMI.openPart && window.HMI.openPart('windowL');
                if (window.HMI && !open) window.HMI.closePart && window.HMI.closePart('windowL');
                break;
            }
            case 'open_service_card': {
                const svc = normalizeServiceName(params.service || params.card || params.name);
                if (svc === 'music') { musicOpen = true; handleMusicBilibili(); }
                else if (svc === 'video' || svc === 'bilibili') { bilibiliOpen = true; handleMusicBilibili(); }
                else if (serviceTemplates[svc]) { upsertCard(svc, 1, serviceTemplates[svc], ''); }
                else { showActionResult('service', 'Service', params.service || svc || 'Open', '服务界面已调出'); }
                break;
            }
            case 'play_music': {
                const title = params.title || 'Music';
                if (!isPlaying && audio) { audio.play(); isPlaying = true; }
                showActionResult('music', 'Now Playing', title, '音乐服务已启动');
                break;
            }
            case 'set_cabin_mode': {
                const mode = params.mode || '舒适';
                showActionResult('mode', 'Cabin Mode', mode, '座舱模式已切换');
                dockCabin.classList.add('active');
                zoneRight.classList.remove('hidden');
                break;
            }
            case 'show_alert': {
                const msg = params.message || '';
                if (msg && window._novaHandleFCMessage) {
                    window._novaHandleFCMessage({ type: 'fc_executed', function: 'show_alert', result: msg });
                }
                if (msg) showActionResult('alert', 'NOVA Alert', 'NOTICE', msg);
                break;
            }
            case 'set_ambient_light': {
                const color = params.color || '蓝';
                document.documentElement.style.setProperty('--accent-cyan', _colorMap(color));
                showActionResult('light', 'Ambient Light', color, '氛围灯已调整');
                break;
            }
            case 'set_destination': {
                const dest = params.destination || params.dest || params.location || '目的地';
                const navDest = document.querySelector('.nav-dest');
                if (navDest) navDest.textContent = dest;
                showActionResult('destination', 'Destination', dest, '导航目的地已更新');
                dockNav.classList.add('active');
                zoneCenter.classList.remove('hidden');
                break;
            }
            case 'change_lane': {
                const direction = params.direction || '左';
                const delta = /右|right/i.test(direction) ? 1 : -1;
                const maxLane = Math.max(1, adasData.lane_count || 3) - 1;
                adasData.ego_lane_index = Math.min(maxLane, Math.max(0, (adasData.ego_lane_index ?? 1) + delta));
                showActionResult('lane', 'Lane Change', /右|right/i.test(direction) ? 'RIGHT' : 'LEFT', '正在执行安全变道');
                dockAdas.classList.add('active');
                zoneLeft.classList.remove('hidden');
                break;
            }
            case 'query_state': {
                showActionResult('query', 'State Query', params.target || 'Vehicle', '已查询当前状态');
                break;
            }
            // ─── Dock 面板控制 ───
            case 'toggle_adas': {
                const show = params.show;
                const hidden = zoneLeft.classList.contains('hidden');
                if (show && hidden) { zoneLeft.classList.remove('hidden'); dockAdas.classList.add('active'); }
                else if (!show && !hidden) { zoneLeft.classList.add('hidden'); dockAdas.classList.remove('active'); }
                break;
            }
            case 'toggle_navigation': {
                const show = params.show;
                const hidden = zoneCenter.classList.contains('hidden');
                if (show && hidden) { zoneCenter.classList.remove('hidden'); dockNav.classList.add('active'); }
                else if (!show && !hidden) { zoneCenter.classList.add('hidden'); dockNav.classList.remove('active'); }
                break;
            }
            case 'toggle_cabin_cards': {
                const show = params.show;
                const hidden = zoneRight.classList.contains('hidden');
                if (show && hidden) { zoneRight.classList.remove('hidden'); dockCabin.classList.add('active'); }
                else if (!show && !hidden) { zoneRight.classList.add('hidden'); dockCabin.classList.remove('active'); }
                break;
            }
            case 'toggle_service_panel': {
                const open = params.open;
                if (open) { servicePanel.classList.add('open'); dockService.classList.add('active'); }
                else { servicePanel.classList.remove('open'); dockService.classList.remove('active'); }
                break;
            }
            case 'toggle_3d_scene': {
                const show = params.show;
                const isOpen = unityOverlay.classList.contains('active');
                if (show && !isOpen) {
                    unityOverlay.classList.add('active'); dock3d.classList.add('active');
                    if (!unityLoaded) { loadUnity(); unityLoaded = true; }
                } else if (!show && isOpen) {
                    unityOverlay.classList.remove('active'); dock3d.classList.remove('active');
                }
                break;
            }
            // ─── Unity 3D 场景控制 ───
            case 'switch_camera':
            case 'reset_camera':
            case 'toggle_car_part':
            case 'open_car_part':
            case 'close_car_part':
            case 'rotate_car': {
                // Auto-open 3D scene if not already visible
                const isOpen = unityOverlay.classList.contains('active');
                if (!isOpen) {
                    unityOverlay.classList.add('active'); dock3d.classList.add('active');
                    if (!unityLoaded) { loadUnity(); unityLoaded = true; }
                }
                if (!window.HMI) break;
                if (funcName === 'switch_camera') window.HMI.switchCamera(params.view);
                else if (funcName === 'reset_camera') window.HMI.sendCommand('resetCamera');
                else if (funcName === 'toggle_car_part') window.HMI.togglePart(params.part);
                else if (funcName === 'open_car_part') window.HMI.openPart(params.part);
                else if (funcName === 'close_car_part') window.HMI.closePart(params.part);
                else if (funcName === 'rotate_car') {
                    if (params.mode === 'absolute') window.HMI.rotateCarTo(params.angle || 0);
                    else if (params.mode === 'relative') window.HMI.rotateCarBy(params.angle || 90);
                    else window.HMI.resetCarRotation();
                }
                break;
            }
        }
    }

    function _colorMap(color) {
        const map = { '蓝': '#00d4ff', '红': '#ff3b30', '绿': '#34c759', '紫': '#7b2dff', '暖白': '#ffd4a0', '橙': '#ff9500' };
        return map[color] || '#00d4ff';
    }

    // 暴露给 voice.js 调用
    window._executeFCAction = _executeFCAction;

    // ─── Init ────────────────────────────────────────────────
    function init() {
        scaleCanvas();
        window.addEventListener('resize', scaleCanvas);
        updateClock();
        setInterval(updateClock, 10000);
        updateLockClock();
        initADAS();
        initNav();
        initWebSocket();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
