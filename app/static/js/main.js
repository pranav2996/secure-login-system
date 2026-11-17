document.addEventListener('DOMContentLoaded', () => {
  const loginBackdrop = document.querySelector('.login-backdrop');
  const ambientCanvas = document.querySelector('.login-ambient-canvas');
  if (ambientCanvas && loginBackdrop) {
    const ctx = ambientCanvas.getContext('2d', { alpha: true });
    const motionOK = !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    const lowPower = (navigator.hardwareConcurrency > 0 && navigator.hardwareConcurrency <= 4)
      || connection?.saveData || ['slow-2g', '2g'].includes(connection?.effectiveType);
    let width = 0, height = 0, frame = 0, last = 0;
    let particles = [];
    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
      width = window.innerWidth; height = window.innerHeight;
      ambientCanvas.width = Math.round(width * dpr); ambientCanvas.height = Math.round(height * dpr);
      ambientCanvas.style.width = `${width}px`; ambientCanvas.style.height = `${height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const count = Math.min(lowPower ? 26 : 54, Math.round(width * height / (lowPower ? 42000 : 25000)));
      particles = Array.from({ length: count }, (_, i) => ({
        x: Math.random() * width, y: Math.random() * height,
        r: 0.6 + Math.random() * 1.6, speed: 0.08 + Math.random() * 0.2,
        phase: Math.random() * Math.PI * 2, cyan: i % 4 !== 0,
      }));
    };
    const draw = now => {
      if (motionOK) frame = requestAnimationFrame(draw);
      if (document.hidden || now - last < (lowPower ? 50 : 33)) return;
      const dt = Math.min((now - last) / 1000 || 0, 0.05); last = now;
      ctx.clearRect(0, 0, width, height);
      const cx = width * 0.49, cy = height * 0.51, radius = Math.min(width * 0.19, height * 0.32, 255);
      // Quiet luminous atmosphere and the fixed holographic globe stay behind all controls.
      const halo = ctx.createRadialGradient(cx, cy, radius * .15, cx, cy, radius * 1.8);
      halo.addColorStop(0, 'rgba(0,205,232,.17)'); halo.addColorStop(.55, 'rgba(24,94,157,.08)'); halo.addColorStop(1, 'rgba(34,29,102,0)');
      ctx.fillStyle = halo; ctx.fillRect(0, 0, width, height);
      ctx.save(); ctx.translate(cx, cy);
      const rotation = motionOK ? now * .000035 : 0;
      ctx.rotate(rotation);
      ctx.strokeStyle = 'rgba(27,215,235,.32)'; ctx.lineWidth = 1;
      for (let i = -2; i <= 2; i++) {
        const w = radius * Math.sqrt(Math.max(.03, 1 - i * i * .12));
        ctx.beginPath(); ctx.ellipse(0, 0, w, radius * (.98 - Math.abs(i) * .08), 0, 0, Math.PI * 2); ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(41,169,222,.23)';
      for (let i = 0; i < 5; i++) { ctx.beginPath(); ctx.ellipse(0, 0, radius * .96, radius * (.22 + i * .14), 0, 0, Math.PI * 2); ctx.stroke(); }
      // Orbital paths and nodes add the cyan/purple holographic depth seen in the reference.
      ctx.rotate(-rotation * 1.5); ctx.strokeStyle = 'rgba(238,177,93,.35)';
      ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.32, radius * .32, -.37, 0, Math.PI * 2); ctx.stroke();
      ctx.strokeStyle = 'rgba(156,100,255,.34)'; ctx.beginPath(); ctx.ellipse(0, 0, radius * 1.42, radius * .27, .45, 0, Math.PI * 2); ctx.stroke();
      ctx.restore();
      // Background-only binary, circuit traces, nodes and drifting particles.
      ctx.font = '600 17px ui-monospace, monospace';
      for (let i = 0; i < 24; i++) {
        const x = ((i * 137 + now * (motionOK ? .009 : 0)) % (width + 40)) - 20;
        const y = ((i * 83 + now * (motionOK ? .018 : 0)) % (height + 30)) - 15;
        ctx.fillStyle = i % 5 === 0 ? 'rgba(174,94,255,.55)' : 'rgba(0,221,241,.54)';
        ctx.fillText(i % 2 ? '1' : '0', x, y);
      }
      ctx.lineWidth = 1;
      for (let i = 0; i < 10; i++) {
        const x = (i * width / 9 + 18) % width, y = i % 2 ? height * .13 : height * .87;
        const bend = i % 2 ? 28 : -28;
        ctx.strokeStyle = 'rgba(29,197,229,.10)'; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + bend, y + (i % 2 ? 38 : -38)); ctx.lineTo(x + bend + 54, y + (i % 2 ? 38 : -38)); ctx.stroke();
        ctx.fillStyle = 'rgba(58,229,247,.55)'; ctx.beginPath(); ctx.arc(x + bend + 54, y + (i % 2 ? 38 : -38), 1.8, 0, Math.PI * 2); ctx.fill();
      }
      particles.forEach(p => {
        if (motionOK) { p.y -= p.speed * dt * 25; p.x += Math.sin(now * .0004 + p.phase) * dt * 4; if (p.y < -4) { p.y = height + 4; p.x = Math.random() * width; } }
        ctx.fillStyle = p.cyan ? 'rgba(93,231,248,.64)' : 'rgba(183,133,255,.54)';
        ctx.shadowBlur = p.r * 5; ctx.shadowColor = p.cyan ? '#25dff1' : '#9c62ef';
        ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill();
      });
      ctx.shadowBlur = 0;
    };
    resize(); window.addEventListener('resize', resize, { passive: true });
    if (motionOK) frame = requestAnimationFrame(draw); else draw(0);
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) cancelAnimationFrame(frame);
      else if (motionOK) { last = 0; frame = requestAnimationFrame(draw); }
    });
  }
  if (loginBackdrop) {
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    const lowPower = navigator.hardwareConcurrency > 0 && navigator.hardwareConcurrency <= 4;
    const dataSaver = connection?.saveData || ['slow-2g', '2g'].includes(connection?.effectiveType);
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (lowPower || dataSaver || reducedMotion) {
      loginBackdrop.classList.add('login-backdrop--fallback');
      loginBackdrop.querySelector('video')?.pause();
    }
  }
  document.querySelectorAll('[data-toggle-password]').forEach(button => {
    button.addEventListener('click', () => {
      const input = document.getElementById(button.dataset.togglePassword);
      const reveal = input.type === 'password';
      input.type = reveal ? 'text' : 'password';
      button.textContent = reveal ? 'Hide' : 'Show';
      button.setAttribute('aria-label', `${reveal ? 'Hide' : 'Show'} password`);
    });
  });
  document.querySelectorAll('.toast-close').forEach(button => button.addEventListener('click', () => button.closest('.toast').remove()));
  const strengthInput = document.querySelector('[data-strength-input]');
  const meter = document.getElementById('strength-meter');
  if (strengthInput && meter) strengthInput.addEventListener('input', () => {
    const p = strengthInput.value;
    const score = [p.length >= 8, p.length >= 12, /[A-Z]/.test(p) && /[a-z]/.test(p), /\d/.test(p), /[^A-Za-z0-9]/.test(p)].filter(Boolean).length;
    meter.style.width = `${score * 20}%`;
    meter.dataset.score = score;
  });
  document.querySelectorAll('[data-copy-codes]').forEach(button => button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(button.dataset.copyCodes); button.textContent = 'Copied'; }
    catch { button.textContent = 'Select the codes to copy'; }
  }));
});
