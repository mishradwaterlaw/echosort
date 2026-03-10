"use client";

import React, { useEffect, useState, useRef } from 'react';
import Link from 'next/link';
import '@/app/landing.css';

export default function HomeUI() {
  const [mounted, setMounted] = useState(false);
  const [sliderPct, setSliderPct] = useState(50);
  const sliderRef = useRef<HTMLDivElement>(null);
  const draggingRef = useRef(false);

  useEffect(() => {
    setMounted(true);

    const handleMove = (clientX: number) => {
      if (!draggingRef.current || !sliderRef.current) return;
      const rect = sliderRef.current.getBoundingClientRect();
      const pct = ((clientX - rect.left) / rect.width) * 100;
      setSliderPct(Math.max(5, Math.min(95, pct)));
    };

    const onMouseMove = (e: MouseEvent) => handleMove(e.clientX);
    const onTouchMove = (e: TouchEvent) => handleMove(e.touches[0].clientX);
    const onMouseUp = () => { draggingRef.current = false; };
    const onTouchEnd = () => { draggingRef.current = false; };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('touchmove', onTouchMove);
    window.addEventListener('mouseup', onMouseUp);
    window.addEventListener('touchend', onTouchEnd);

    // Scroll reveal
    const reveals = document.querySelectorAll('.reveal');
    const obs = new IntersectionObserver((entries) => {
      entries.forEach(e => {
        if (e.isIntersecting) e.target.classList.add('visible');
      });
    }, { threshold: 0.1 });
    reveals.forEach(r => obs.observe(r));

    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('touchmove', onTouchMove);
      window.removeEventListener('mouseup', onMouseUp);
      window.removeEventListener('touchend', onTouchEnd);
      obs.disconnect();
    };
  }, []);

  return (
    <div className="landing-body">
      {/* NAV */}
      <nav>
        <Link href="/" className="nav-brand">Echo<span>Sort</span></Link>
        <div className="nav-links">
          <a href="#how">How it Works</a>
          <a href="#privacy">Privacy</a>
          <a href="#usecases">Use Cases</a>
          <Link href="/dashboard" className="nav-cta">Organizer Login</Link>
        </div>
      </nav>

      {/* HERO */}
      <div className="hero">
        <div className="hero-mesh"></div>
        <div className="echo-rings">
          <div className="ring"></div>
          <div className="ring"></div>
          <div className="ring"></div>
          <div className="ring"></div>
        </div>

        <div className="hero-content">
          <div className="hero-eyebrow">AI-Powered Photo Discovery</div>
          <h1 className="hero-headline">
            Your Face<br />is the <em>Filter.</em>
          </h1>
          <p className="hero-sub">
            Stop scrolling through thousands of event photos. Upload a selfie and Echo Sort instantly finds every shot of you.
          </p>
          <div className="hero-actions">
            <Link href="/find" className="btn-primary">Find My Photos →</Link>
            <Link href="/dashboard" className="btn-ghost">I&apos;m an Organizer</Link>
          </div>
        </div>

        <div className="hero-visual">
          <div className="split-demo">
            {/* LEFT: chaos */}
            <div className="demo-side demo-side-left">
              <div className="demo-label">Before — 1,247 photos</div>
              <div className="photo-chaos" id="photoChaos">
                {mounted && Array.from({ length: 40 }).map((_, i) => {
                  const isHighlight = Math.random() > 0.85;
                  const bgUrl = isHighlight 
                    ? "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200&h=200&fit=crop" // the target girl
                    : [
                        "https://images.unsplash.com/photo-1540039155732-6804a9af8288?w=200&h=200&fit=crop", // concert
                        "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=200&h=200&fit=crop", // concert
                        "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=200&h=200&fit=crop", // group
                        "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=200&h=200&fit=crop", // party
                        "https://images.unsplash.com/photo-1506157786151-b8491531f063?w=200&h=200&fit=crop", // dj
                        "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&h=200&fit=crop"  // random portrait
                      ][i % 6];

                  return (
                    <div 
                      key={i} 
                      className={`photo-tile ${isHighlight ? 'highlight' : ''}`}
                      style={{ backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center' }}
                    ></div>
                  );
                })}
              </div>
            </div>
            {/* RIGHT: sorted */}
            <div className="demo-side demo-side-right">
              <div className="demo-label">After — 14 photos of you</div>
              <div className="match-count">✓ 14 matches</div>
              <div className="photo-sorted">
                {mounted && Array.from({ length: 9 }).map((_, i) => {
                  // A consistent set of photos of the *exact same woman* (the girl with the bun from the left side)
                  // to prove the AI filtered correctly
                  const targetPhotos = [
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop", // main portrait
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.4&fp-z=1.2", // zoomed out
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.3&fp-z=1.4", // zoomed higher
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.25&fp-z=1.5", // focused on face
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.4&fp-y=0.35&fp-z=1.4", // off-center left
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.6&fp-y=0.35&fp-z=1.4", // off-center right
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.45&fp-y=0.4&fp-z=1.1", // slight zoom
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.55&fp-y=0.4&fp-z=1.1", // slight zoom right
                    "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.5&fp-z=1.3" // center lower
                  ];
                  return (
                    <div 
                      key={i} 
                      className={`photo-tile ${i % 2 === 0 ? 'highlight' : ''}`}
                      style={{ 
                        backgroundImage: `url(${targetPhotos[i % targetPhotos.length]})`, 
                        backgroundSize: 'cover', 
                        backgroundPosition: 'center' 
                      }}
                    ></div>
                  );
                })}
              </div>
              <div 
                className="selfie-badge"
                style={{ 
                  backgroundImage: `url(https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=100&h=100&fit=crop&q=80&crop=faces)`, 
                  backgroundSize: 'cover', 
                  backgroundPosition: 'center', 
                  color: 'transparent' 
                }}
              >📸</div>
            </div>
          </div>
        </div>
      </div>

      {/* HOW IT WORKS */}
      <section className="how-it-works reveal" id="how">
        <div className="section-eyebrow">How it Works</div>
        <h2 className="section-title">Three steps to <em>your</em> memories</h2>
        <div className="steps-grid">
          <div className="step">
            <div className="step-number">01 / 03</div>
            <div className="step-icon">🎟</div>
            <div className="step-title">Join the Event</div>
            <div className="step-desc">Scan the organizer&apos;s QR code or open the shared link. No app download required — it runs entirely in your browser.</div>
          </div>
          <div className="step">
            <div className="step-number">02 / 03</div>
            <div className="step-icon">📷</div>
            <div className="step-title">The Echo Snap</div>
            <div className="step-desc">Take a quick selfie using your camera or upload a photo. This is your search key — it&apos;s processed instantly and never stored beyond your session.</div>
          </div>
          <div className="step">
            <div className="step-number">03 / 03</div>
            <div className="step-icon">⚡</div>
            <div className="step-title">Instant Results</div>
            <div className="step-desc">Our AI echoes back every photo you&apos;re in from the entire event gallery. Download them all in one click.</div>
          </div>
        </div>
      </section>

      {/* INTERACTIVE DEMO */}
      <section className="demo-section reveal" id="demo">
        <div className="section-eyebrow">Interactive Demo</div>
        <h2 className="section-title">See the <em>echo</em> in action</h2>
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem', fontWeight: 300, marginBottom: 0 }}>
          Drag the slider to see the difference between a raw photo dump and an Echo Sorted gallery.
        </p>

        <div
          className="slider-container"
          id="sliderDemo"
          ref={sliderRef}
          onMouseDown={() => { draggingRef.current = true; }}
          onTouchStart={() => { draggingRef.current = true; }}
        >
          {/* BEFORE */}
          <div className="slider-before">
            <div className="slider-before-grid" id="beforeGrid">
              {mounted && Array.from({ length: 40 }).map((_, i) => {
                const isHighlight = Math.random() > 0.85; // ~15% chance to show the target girl
                const bgUrl = isHighlight 
                  ? "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=200&h=200&fit=crop" // the target girl
                  : [
                      "https://images.unsplash.com/photo-1540039155732-6804a9af8288?w=200&h=200&fit=crop", // concert
                      "https://images.unsplash.com/photo-1514525253161-7a46d19cd819?w=200&h=200&fit=crop", // concert
                      "https://images.unsplash.com/photo-1516450360452-9312f5e86fc7?w=200&h=200&fit=crop", // group
                      "https://images.unsplash.com/photo-1533174072545-7a4b6ad7a6c3?w=200&h=200&fit=crop", // party
                      "https://images.unsplash.com/photo-1506157786151-b8491531f063?w=200&h=200&fit=crop", // dj
                      "https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?w=200&h=200&fit=crop"  // random portrait
                    ][i % 6];
                return (
                  <div 
                    key={i} 
                    className="grid-tile"
                    style={{ backgroundImage: `url(${bgUrl})`, backgroundSize: 'cover', backgroundPosition: 'center', opacity: isHighlight ? 0.9 : 0.4 }}
                  ></div>
                );
              })}
            </div>
            <div className="scan-line"></div>
            <span className="slider-tag tag-before">Raw Dump</span>
            <div className="slider-label">1,247 unfiltered photos</div>
          </div>

          {/* AFTER */}
          <div
            className="slider-after"
            id="sliderAfter"
            style={{ clipPath: `inset(0 ${100 - sliderPct}% 0 0)` }}
          >
            <div className="slider-after-grid" id="afterGrid">
              {mounted && Array.from({ length: 12 }).map((_, i) => {
                const targetPhotos = [
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop", 
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.4&fp-z=1.2", 
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.3&fp-z=1.4",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.4&fp-y=0.35&fp-z=1.4",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.6&fp-y=0.35&fp-z=1.4",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.4&fp-y=0.45&fp-z=1.2",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.6&fp-y=0.45&fp-z=1.2",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.5&fp-z=1.3",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.45&fp-y=0.4&fp-z=1.1",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.55&fp-y=0.4&fp-z=1.1",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.25&fp-z=1.5",
                  "https://images.unsplash.com/photo-1544005313-94ddf0286df2?w=400&h=400&fit=crop&q=80&crop=focalpoint&fp-x=0.5&fp-y=0.4&fp-z=1.0"
                ];
                return (
                  <div 
                    key={i} 
                    className="grid-tile active"
                    style={{ 
                      backgroundImage: `url(${targetPhotos[i % targetPhotos.length]})`, 
                      backgroundSize: 'cover', 
                      backgroundPosition: 'center'
                    }}
                  ></div>
                );
              })}
            </div>
            <span className="slider-tag tag-after">Echo Sorted</span>
            <div className="slider-label">14 photos of you</div>
          </div>

          <div
            className="slider-handle"
            id="sliderHandle"
            style={{ left: `${sliderPct}%` }}
          ></div>
        </div>
      </section>

      {/* PRIVACY */}
      <section className="privacy-section reveal" id="privacy">
        <div className="section-eyebrow">Privacy & Security</div>
        <h2 className="section-title">Privacy <em>by design,</em><br />not by policy</h2>
        <div className="privacy-grid">
          <div className="privacy-card">
            <div className="privacy-icon">🔐</div>
            <div className="privacy-title">Selfies are session-only</div>
            <div className="privacy-desc">Your search selfie is converted to a mathematical vector and immediately discarded. We identify a face&apos;s geometry — we never store the image itself.</div>
          </div>
          <div className="privacy-card">
            <div className="privacy-icon">🛡</div>
            <div className="privacy-title">No facial database</div>
            <div className="privacy-desc">We don&apos;t build profiles. Each search is stateless. Your face geometry is computed on-demand and cleared after your session expires.</div>
          </div>
          <div className="privacy-card">
            <div className="privacy-icon">🔒</div>
            <div className="privacy-title">Bank-grade encryption</div>
            <div className="privacy-desc">All photos are stored in private buckets with time-limited signed URLs. No photo is ever publicly accessible — only you can see your matches.</div>
          </div>
          <div className="privacy-card">
            <div className="privacy-icon">⚖️</div>
            <div className="privacy-title">GDPR compliant</div>
            <div className="privacy-desc">Data minimisation at every layer. Event organisers can purge all photos and embeddings instantly. You can request deletion at any time.</div>
          </div>
        </div>
        <div>
          <span className="privacy-badge">
            <span>🛡</span> Privacy First — No Face Profiles Stored
          </span>
        </div>
      </section>

      {/* USE CASES */}
      <section className="usecases-section reveal" id="usecases">
        <div className="section-eyebrow">Use Cases</div>
        <h2 className="section-title">Built for every <em>moment</em></h2>
        <div className="cases-grid">
          <div className="case-card">
            <div className="case-visual">💍</div>
            <div className="case-body">
              <div className="case-tag">Weddings</div>
              <div className="case-title">Give guests their memories instantly</div>
              <div className="case-desc">No more waiting weeks for the photographer to tag everyone. Every guest finds their photos the same night.</div>
            </div>
          </div>
          <div className="case-card">
            <div className="case-visual">🏃</div>
            <div className="case-body">
              <div className="case-tag">Marathons & Sports</div>
              <div className="case-title">Find your finish line photo</div>
              <div className="case-desc">In a sea of 10,000 runners, find your exact crossing moment in seconds — not hours of scrolling.</div>
            </div>
          </div>
          <div className="case-card">
            <div className="case-visual">🎪</div>
            <div className="case-body">
              <div className="case-tag">Festivals & Events</div>
              <div className="case-title">Capture the vibe, find the squad</div>
              <div className="case-desc">Multi-day festivals generate thousands of photos. Echo Sort cuts through the noise instantly.</div>
            </div>
          </div>
        </div>
      </section>

      {/* FOOTER CTA */}
      <div className="footer-cta reveal">
        <div className="footer-cta-rings">
          <div className="echo-rings">
            <div className="ring"></div>
            <div className="ring"></div>
            <div className="ring"></div>
          </div>
        </div>
        <h2>Ready to make your event<br /><em>unforgettable?</em></h2>
        <p>Join organizers who trust Echo Sort to deliver memories instantly.</p>
        <Link href="/dashboard" className="btn-primary">Create an Event Gallery →</Link>
      </div>

      {/* FOOTER */}
      <footer>
        <span>© 2026 EchoSort</span>
        <span>Built with ArcFace · pgvector · Next.js</span>
        <span>Privacy First</span>
      </footer>
    </div>
  );
}
