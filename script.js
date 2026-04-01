/* ============================================================
   WHALE TREND – Shadow Whale Follower | Main Script
   ============================================================ */

gsap.registerPlugin(ScrollTrigger, TextPlugin);

// ── PARTICLE BACKGROUND (Three.js) ─────────────────────────
(function initParticles() {
  const canvas = document.getElementById('bg-canvas');
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.z = 5;

  // Particle geometry
  const count = window.innerWidth < 768 ? 800 : 2000;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const sizes = new Float32Array(count);

  const c1 = new THREE.Color('#00d4ff');
  const c2 = new THREE.Color('#7b2fff');
  const c3 = new THREE.Color('#ffffff');

  for (let i = 0; i < count; i++) {
    positions[i * 3]     = (Math.random() - 0.5) * 25;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 15;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 10;

    const r = Math.random();
    const col = r < 0.4 ? c1 : r < 0.7 ? c2 : c3;
    colors[i * 3]     = col.r;
    colors[i * 3 + 1] = col.g;
    colors[i * 3 + 2] = col.b;
    sizes[i] = Math.random() * 2.5 + 0.5;
  }

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
  geo.setAttribute('size', new THREE.BufferAttribute(sizes, 1));

  const mat = new THREE.PointsMaterial({
    size: 0.03,
    vertexColors: true,
    transparent: true,
    opacity: 0.6,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  const points = new THREE.Points(geo, mat);
  scene.add(points);

  let mouseX = 0, mouseY = 0;
  document.addEventListener('mousemove', e => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 0.3;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 0.2;
  });

  window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  });

  const clock = new THREE.Clock();
  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();
    points.rotation.y = t * 0.015 + mouseX;
    points.rotation.x = mouseY * 0.5;
    renderer.render(scene, camera);
  }
  animate();
})();

// ── CUSTOM CURSOR ───────────────────────────────────────────
(function initCursor() {
  const ghost = document.getElementById('ghost-cursor');
  const dot   = document.getElementById('cursor-dot');
  let mx = 0, my = 0, gx = 0, gy = 0;
  let isVisible = false;

  document.addEventListener('mousemove', e => {
    mx = e.clientX; my = e.clientY;
    if (!isVisible) {
      if(ghost) ghost.classList.add('visible');
      isVisible = true;
    }
  }, { passive: true });

  document.addEventListener('mouseleave', () => {
    if(ghost) ghost.classList.remove('visible');
    isVisible = false;
  });

  function lerpGhost() {
    if(dot) {
      dot.style.left = mx + 'px';
      dot.style.top  = my + 'px';
    }
    if(ghost) {
      gx += (mx - gx) * 0.08;
      gy += (my - gy) * 0.08;
      ghost.style.left = gx + 'px';
      ghost.style.top  = gy + 'px';
    }
    requestAnimationFrame(lerpGhost);
  }
  lerpGhost();

  // Enlarge magnifier on interactive elements
  document.querySelectorAll('a, button, input, [data-step]').forEach(el => {
    el.addEventListener('mouseenter', () => ghost.classList.add('hover'));
    el.addEventListener('mouseleave', () => ghost.classList.remove('hover'));
  });
})();

// ── NAVBAR SCROLL ───────────────────────────────────────────
(function initNav() {
  const nav = document.getElementById('navbar');
  window.addEventListener('scroll', () => {
    nav.classList.toggle('scrolled', window.scrollY > 50);
  }, { passive: true });

  const hamburger = document.getElementById('hamburger');
  hamburger.addEventListener('click', () => {
    const links = nav.querySelector('.nav-links');
    const btn   = nav.querySelector('.btn-nav');
    if (links) {
      const open = links.style.display === 'flex';
      links.style.display = open ? 'none' : 'flex';
      links.style.flexDirection = 'column';
      links.style.position = 'absolute';
      links.style.top = '70px';
      links.style.left = '0';
      links.style.right = '0';
      links.style.background = 'rgba(4,4,10,0.97)';
      links.style.padding = '1.5rem 2rem';
      links.style.borderBottom = '1px solid rgba(0,212,255,0.2)';
      if (btn) btn.style.display = open ? 'none' : 'block';
    }
  });
})();

// ── SCROLL REVEAL ───────────────────────────────────────────
(function initReveal() {
  const els = document.querySelectorAll('.step-card, .benefit-item, .section-label, .section-title, .section-sub, .mockup-ui, .terminal-wrap, .agent-tier-box');
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e, i) => {
      if (e.isIntersecting) {
        setTimeout(() => e.target.classList.add('visible'), i * 80);
        io.unobserve(e.target);
      }
    });
  }, { threshold: 0.15 });
  els.forEach(el => { el.classList.add('reveal'); io.observe(el); });
})();

// ── COUNTER ANIMATION ───────────────────────────────────────
(function initCounters() {
  const counters = document.querySelectorAll('.stat-num[data-target]');
  const io = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        const el = entry.target;
        const target = parseInt(el.dataset.target);
        const duration = 2000;
        const step = target / (duration / 16);
        let current = 0;
        const timer = setInterval(() => {
          current += step;
          if (current >= target) { current = target; clearInterval(timer); }
          el.textContent = Math.floor(current).toLocaleString();
        }, 16);
        io.unobserve(el);
      }
    });
  }, { threshold: 0.5 });
  counters.forEach(c => io.observe(c));
})();

// ── LIVE TERMINAL ───────────────────────────────────────────
(function initTerminal() {
  const body = document.getElementById('terminal-body');
  if (!body) return;

  const wallets = [
    '0x3f4...a821', '0xd92...c147', '0x7a1...f039', '0xb55...2e8a',
    '0x1c3...d762', '0x9e8...5b31', '0x4f7...9c20', '0x2d6...e481',
  ];
  const tokens = ['$PEPE', '$WIF', '$BONK', '$SHIB', '$DOGE', '$ARB', '$OP', '$SOL', '$ETH', '$BTC'];
  const alerts = [
    ['warn', '⚠  Whale sentiment mismatch detected — 0x3f4...a821'],
    ['alert', '🧠 Potential dump signal — shilling $PEPE, selling $800K'],
    ['warn', '⚠  Social divergence score: 94/100 — EXIT RISK HIGH'],
    ['alert', '🚨 Coordinated narrative detected — 3 wallets, 1 token'],
    ['warn', '⚠  Insider wallet: 72hr pre-pump accumulation pattern'],
    ['alert', '🧠 Exit liquidity trap forming — $WIF — estimated $2.1M'],
    ['info', '✅ Clean wallet confirmed — 0xb55...2e8a — NO mismatch'],
    ['warn', '⚠  Whale Trend score: 0x9e8...5b31 → SUSPICIOUS (87/100)'],
  ];

  let alertIdx = 0;
  let scanning = false;

  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting && !scanning) {
        scanning = true;
        runTerminal();
        io.disconnect();
      }
    });
  }, { threshold: 0.4 });
  io.observe(body);

  function addLine(cls, text, delay) {
    return new Promise(resolve => {
      setTimeout(() => {
        const line = document.createElement('div');
        line.className = `term-line ${cls}`;
        line.textContent = text;
        body.appendChild(line);
        body.scrollTop = body.scrollHeight;
        resolve();
      }, delay);
    });
  }

  async function runTerminal() {
    let delay = 200;
    const interval = 1600;

    async function cycle() {
      const w = wallets[Math.floor(Math.random() * wallets.length)];
      const t = tokens[Math.floor(Math.random() * tokens.length)];

      await addLine('info', `[SCAN] Analyzing wallet ${w}...`, delay);
      delay += interval * 0.4;
      await addLine('', `       Token: ${t} | Social posts: ${Math.floor(Math.random()*12+1)} in 24h`, delay);
      delay += interval * 0.4;

      const isAlert = Math.random() > 0.35;
      if (isAlert) {
        const [cls, msg] = alerts[alertIdx % alerts.length];
        alertIdx++;
        await addLine(cls, msg, delay);
      } else {
        await addLine('ok', `[OK]   Wallet ${w} — behavior consistent`, delay);
      }
      delay += interval;

      // Keep terminal from growing too long
      const lines = body.querySelectorAll('.term-line');
      if (lines.length > 30) {
        for (let i = 0; i < 5; i++) lines[i].remove();
      }

      // Add blinking cursor at end temporarily
      const cursor = document.createElement('span');
      cursor.className = 'term-cursor';
      body.appendChild(cursor);
      setTimeout(() => { cursor.remove(); cycle(); }, interval);
    }
    cycle();
  }
})();

// ── GSAP SCROLL ANIMATIONS ──────────────────────────────────
(function initScrollAnimations() {
  // Hero headline entrance
  gsap.from('#hero-content', {
    opacity: 0,
    y: 60,
    duration: 1.2,
    ease: 'power3.out',
    delay: 0.3,
  });

  // Whale image 3D mouse parallax bouncy tilt
  const whaleImg = document.getElementById('whale-img');
  if (whaleImg) {
    // Add a smooth bouncy transition so it feels fluid
    whaleImg.style.transition = 'transform 0.25s cubic-bezier(0.2, 0.8, 0.2, 1)';
    whaleImg.style.transformOrigin = 'center center';
    
    let w_rx = 0, w_ry = 0, w_tx = 0, w_ty = 0;
    let w_ticking = false;

    document.addEventListener('mousemove', e => {
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      const dx = (e.clientX - cx) / cx;  // -1 to 1
      const dy = (e.clientY - cy) / cy;
      
      w_rx = dy * -15;  // more aggressive tilt X
      w_ry = dx * 18;   // more aggressive tilt Y
      w_tx = dx * 30;   // translate px
      w_ty = dy * 20;
      
      if (!w_ticking) {
        requestAnimationFrame(() => {
          whaleImg.style.transform = `perspective(1200px) rotateX(${w_rx}deg) rotateY(${w_ry}deg) translateX(${w_tx}px) translateY(${w_ty}px) scale(1.08)`;
          w_ticking = false;
        });
        w_ticking = true;
      }
    }, { passive: true });
    
    document.addEventListener('mouseleave', () => {
      whaleImg.style.transform = `perspective(1200px) rotateX(0deg) rotateY(0deg) translateX(0px) translateY(0px) scale(1)`;
    });
  }

  // Fade whale on scroll
  ScrollTrigger.create({
    trigger: '#hero',
    start: 'top top',
    end: 'bottom top',
    scrub: true,
    onUpdate: (self) => {
      if (whaleImg) {
        whaleImg.style.opacity = Math.max(0, 0.88 - self.progress * 1.2);
        whaleImg.style.filter = `drop-shadow(0 0 ${40 + self.progress * 60}px rgba(0,212,255,${0.5 + self.progress * 0.3})) brightness(${1.1 + self.progress * 0.3})`;
      }
    }
  });

  // Section parallax
  gsap.utils.toArray('section').forEach(sec => {
    gsap.from(sec, {
      scrollTrigger: { trigger: sec, start: 'top 80%', end: 'top 20%', scrub: 0.5 },
    });
  });
})();

// ── GLITCH on hero headline ─────────────────────────────────
(function initGlitch() {
  const headline = document.querySelector('.hero-headline');
  if (!headline) return;
  headline.classList.add('glitch');
  headline.setAttribute('data-text', headline.textContent);
})();

// ── NEON BUTTON PULSE ───────────────────────────────────────
(function initBtnPulse() {
  const primaryBtns = document.querySelectorAll('.btn-primary');
  primaryBtns.forEach(btn => {
    gsap.to(btn, {
      boxShadow: '0 0 40px rgba(0,212,255,0.7), 0 0 80px rgba(0,212,255,0.3)',
      duration: 1.5,
      repeat: -1,
      yoyo: true,
      ease: 'sine.inOut',
    });
  });
})();

// ── STEP CARDS HOVER GLOW ───────────────────────────────────
(function initCardEffects() {
  document.querySelectorAll('.step-card').forEach(card => {
    let rect = null;
    let ticking = false;
    
    card.addEventListener('mouseenter', () => {
      rect = card.getBoundingClientRect();
    });
    
    window.addEventListener('scroll', () => { rect = null; }, { passive: true });

    card.addEventListener('mousemove', e => {
      if (!rect) rect = card.getBoundingClientRect();
      const x = ((e.clientX - rect.left) / rect.width) * 100;
      const y = ((e.clientY - rect.top) / rect.height) * 100;
      
      if (!ticking) {
        requestAnimationFrame(() => {
          card.style.background = `radial-gradient(circle at ${x}% ${y}%, rgba(0,212,255,0.08), rgba(255,255,255,0.025) 60%)`;
          ticking = false;
        });
        ticking = true;
      }
    });

    card.addEventListener('mouseleave', () => {
      card.style.background = 'var(--bg-card)';
    });
  });
})();

// ── 3D TILT EFFECT ──────────────────────────────────────────
(function init3DTilt() {
  const tiltElements = document.querySelectorAll('.step-card, .mockup-ui, .terminal, .agent-tier-box, .target-card, .hero-headline, .hero-sub, .hero-badge, .stat-item');
  
  tiltElements.forEach(el => {
    let rect = null;
    let ticking = false;

    el.addEventListener('mouseenter', () => {
      el.style.transition = 'transform 0.1s ease-out';
      el.style.transformStyle = 'preserve-3d';
      rect = el.getBoundingClientRect();
    });
    
    window.addEventListener('scroll', () => { rect = null; }, { passive: true });

    el.addEventListener('mousemove', e => {
      if (!rect) rect = el.getBoundingClientRect();
      const x = e.clientX - rect.left; 
      const y = e.clientY - rect.top;  
      const centerX = rect.width / 2;
      const centerY = rect.height / 2;
      
      const rotateX = ((y - centerY) / centerY) * -15; 
      const rotateY = ((x - centerX) / centerX) * 15;
      
      if (!ticking) {
        requestAnimationFrame(() => {
          el.style.transform = `perspective(1000px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) scale3d(1.03, 1.03, 1.03)`;
          
          // Dynamic neon glow for main cards
          if(el.classList.contains('step-card') || el.classList.contains('mockup-ui') || el.classList.contains('terminal') || el.classList.contains('agent-tier-box')) {
            el.style.boxShadow = `${-rotateY * 2}px ${rotateX * 2}px 30px rgba(0, 212, 255, 0.2), inset 0 0 20px rgba(0, 212, 255, 0.05)`;
          } else if (el.classList.contains('hero-headline')) {
             el.style.textShadow = `${-rotateY}px ${rotateX}px 20px rgba(0, 212, 255, 0.6)`;
          }
          ticking = false;
        });
        ticking = true;
      }
    });

    el.addEventListener('mouseleave', () => {
      el.style.transition = 'transform 0.5s ease-out, box-shadow 0.5s ease-out, text-shadow 0.5s ease-out';
      el.style.transform = `perspective(1000px) rotateX(0deg) rotateY(0deg) scale3d(1, 1, 1)`;
      
      if(el.classList.contains('step-card') || el.classList.contains('mockup-ui') || el.classList.contains('terminal') || el.classList.contains('agent-tier-box')) {
        el.style.boxShadow = '';
      } else if (el.classList.contains('hero-headline')) {
         el.style.textShadow = '';
      }
    });
  });
})();

// ── PAGE LOAD SEQUENCE ──────────────────────────────────────
window.addEventListener('load', () => {
  document.body.style.opacity = '0';
  document.body.style.transition = 'opacity 0.6s ease';
  setTimeout(() => { document.body.style.opacity = '1'; }, 100);
});
