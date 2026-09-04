import os
from selenium import webdriver
from selenium.webdriver.edge.options import Options

svg_content = """<svg width="1920" height="1080" viewBox="0 0 1920 1080" fill="none" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <!-- Background Gradients -->
    <linearGradient id="bgGrad" x1="0" y1="0" x2="1920" y2="1080" gradientUnits="userSpaceOnUse">
      <stop offset="0%" stop-color="#030805"/>
      <stop offset="40%" stop-color="#06150F"/>
      <stop offset="75%" stop-color="#081A13"/>
      <stop offset="100%" stop-color="#020604"/>
    </linearGradient>

    <!-- Ambient Glows -->
    <radialGradient id="centerGlow" cx="0.5" cy="0.45" r="0.55">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.22"/>
      <stop offset="45%" stop-color="#0D9488" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#030805" stop-opacity="0"/>
    </radialGradient>

    <radialGradient id="bananaAmbientGlow" cx="0.5" cy="0.42" r="0.35">
      <stop offset="0%" stop-color="#FACC15" stop-opacity="0.28"/>
      <stop offset="50%" stop-color="#CA8A04" stop-opacity="0.06"/>
      <stop offset="100%" stop-color="#030805" stop-opacity="0"/>
    </radialGradient>

    <!-- Metallic Gold & Neon Gradients -->
    <linearGradient id="titleGoldGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#FFFFFF"/>
      <stop offset="30%" stop-color="#FEF08A"/>
      <stop offset="70%" stop-color="#FACC15"/>
      <stop offset="100%" stop-color="#EAB308"/>
    </linearGradient>

    <linearGradient id="bananaBodyGrad" x1="0.2" y1="0.8" x2="0.8" y2="0.1">
      <stop offset="0%" stop-color="#F59E0B"/>
      <stop offset="25%" stop-color="#FACC15"/>
      <stop offset="60%" stop-color="#FEF08A"/>
      <stop offset="90%" stop-color="#FACC15"/>
      <stop offset="100%" stop-color="#CA8A04"/>
    </linearGradient>

    <linearGradient id="bananaInnerHighlight" x1="0.3" y1="0.7" x2="0.7" y2="0.2">
      <stop offset="0%" stop-color="#FACC15" stop-opacity="0.1"/>
      <stop offset="50%" stop-color="#FFFFFF" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#FEF08A" stop-opacity="0.1"/>
    </linearGradient>

    <linearGradient id="shieldBorderGrad" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#FACC15"/>
      <stop offset="45%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#0D9488"/>
    </linearGradient>

    <linearGradient id="shieldFillGrad" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#10B981" stop-opacity="0.15"/>
      <stop offset="60%" stop-color="#064E3B" stop-opacity="0.08"/>
      <stop offset="100%" stop-color="#020805" stop-opacity="0.3"/>
    </linearGradient>

    <linearGradient id="curveGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#EF4444" stop-opacity="0.3"/>
      <stop offset="25%" stop-color="#10B981" stop-opacity="0.8"/>
      <stop offset="60%" stop-color="#10B981"/>
      <stop offset="100%" stop-color="#FACC15"/>
    </linearGradient>

    <!-- Filters for Glows -->
    <filter id="heroGlow" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="18" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <filter id="subtleGlow" x="-20%" y="-20%" width="140%" height="140%">
      <feGaussianBlur stdDeviation="4" result="blur"/>
      <feComposite in="SourceGraphic" in2="blur" operator="over"/>
    </filter>

    <!-- Clean Geometric Grid Background -->
    <pattern id="cleanGrid" width="60" height="60" patternUnits="userSpaceOnUse">
      <path d="M 60 0 L 0 0 0 60" fill="none" stroke="#10B981" stroke-width="0.7" stroke-opacity="0.12"/>
      <circle cx="60" cy="60" r="1" fill="#FACC15" fill-opacity="0.25"/>
    </pattern>
  </defs>

  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&amp;family=Playfair+Display:wght@700;800;900&amp;family=Plus+Jakarta+Sans:wght@400;500;600;700;800&amp;display=swap');
    
    .font-serif { font-family: 'Playfair Display', Georgia, serif; }
    .font-sans { font-family: 'Plus Jakarta Sans', system-ui, -apple-system, sans-serif; }
    .font-mono { font-family: 'JetBrains Mono', 'Courier New', monospace; }
  </style>

  <!-- Background Base -->
  <rect width="1920" height="1080" fill="url(#bgGrad)"/>
  <rect width="1920" height="1080" fill="url(#cleanGrid)"/>
  <rect width="1920" height="1080" fill="url(#centerGlow)"/>
  <rect width="1920" height="1080" fill="url(#bananaAmbientGlow)"/>

  <!-- Top Accent Rule -->
  <rect x="0" y="0" width="1920" height="3" fill="url(#shieldBorderGrad)"/>

  <!-- ==================== MINIMAL HEADER BADGE ==================== -->
  <g transform="translate(0, 75)">
    <g transform="translate(960, 0)">
      <!-- Centered Hackathon Eyebrow Pill -->
      <rect x="-190" y="0" width="380" height="34" rx="17" fill="#0A1E15" stroke="#10B981" stroke-width="1.2" stroke-opacity="0.6"/>
      <circle cx="-165" cy="17" r="4" fill="#10B981" filter="url(#subtleGlow)"/>
      <text x="-148" y="22" fill="#E2E8F0" class="font-mono" font-size="11.5" font-weight="700" letter-spacing="2">ALPACA HACKATHON 2026</text>
      <text x="110" y="22" fill="#FACC15" class="font-mono" font-size="11" font-weight="700">● LIVE</text>
    </g>
  </g>

  <!-- ==================== CENTER HERO: ICONIC NANO BANANA SHIELD ==================== -->
  <g transform="translate(960, 360)">

    <!-- Background Concentric Shield Rings -->
    <circle cx="0" cy="0" r="230" fill="none" stroke="#10B981" stroke-width="1" stroke-opacity="0.12" stroke-dasharray="8,8"/>
    <circle cx="0" cy="0" r="175" fill="none" stroke="#FACC15" stroke-width="1.2" stroke-opacity="0.18"/>
    
    <!-- Hero Aegis Hex Shield Base -->
    <polygon points="0,-145 125,-72 125,72 0,145 -125,72 -125,-72" 
             fill="url(#shieldFillGrad)" stroke="url(#shieldBorderGrad)" stroke-width="2.5" filter="url(#heroGlow)"/>
    
    <!-- Inner Concentric Hexagon Wireframe -->
    <polygon points="0,-125 108,-62 108,62 0,125 -108,62 -108,-62" 
             fill="none" stroke="#10B981" stroke-width="1" stroke-opacity="0.4" stroke-dasharray="4,4"/>

    <!-- Dynamic Options Hedge Payoff Wave Sweeping Behind Banana -->
    <path d="M -260 80 Q -140 80 -40 -10 T 60 -60 T 260 -60" 
          fill="none" stroke="url(#curveGrad)" stroke-width="3" filter="url(#subtleGlow)"/>
    
    <!-- Hedge Floor Reference Line -->
    <line x1="-240" y1="80" x2="-40" y2="80" stroke="#10B981" stroke-width="2" stroke-dasharray="4,4"/>
    <circle cx="-40" cy="80" r="4" fill="#10B981" filter="url(#subtleGlow)"/>

    <!-- ==================== THE NANO BANANA ICON ==================== -->
    <g transform="translate(-56, -72) scale(1.75)">
      <!-- Banana Body (Curved, Modern, Cyberpunk Finish) -->
      <path d="M 8 72 C 16 80, 38 78, 52 58 C 64 42, 66 22, 58 6 C 54 15, 48 27, 34 40 C 22 52, 12 62, 8 72 Z" 
            fill="url(#bananaBodyGrad)" stroke="#CA8A04" stroke-width="1" filter="url(#subtleGlow)"/>
      
      <!-- Banana Gloss Highlight Ribbon -->
      <path d="M 12 68 C 18 74, 34 72, 46 54 C 56 40, 58 24, 52 12 C 48 20, 42 32, 30 44 C 20 54, 14 62, 12 68 Z" 
            fill="url(#bananaInnerHighlight)"/>
      
      <!-- Banana Stem (Nanotech Emerald Tip) -->
      <path d="M 58 6 C 60 3, 64 2, 67 4 C 65 8, 62 11, 58 11 Z" fill="#65A30D" stroke="#4D7C0F" stroke-width="0.8"/>
      
      <!-- Cybernetic HUD Visor on Banana -->
      <polygon points="28,34 48,25 53,31 33,42" fill="#04120B" stroke="#00FFFF" stroke-width="1.2"/>
      <line x1="30" y1="37" x2="50" y2="28" stroke="#00FFFF" stroke-width="1.6" filter="url(#subtleGlow)"/>

      <!-- Nano Circuit Accent Nodes -->
      <circle cx="34" cy="52" r="1.8" fill="#FACC15"/>
      <line x1="34" y1="52" x2="26" y2="60" stroke="#10B981" stroke-width="0.8" stroke-dasharray="2,2"/>
      <circle cx="26" cy="60" r="1.5" fill="#10B981"/>
    </g>

    <!-- Ambient Orbital Nodes -->
    <g transform="translate(130, -30)">
      <circle cx="0" cy="0" r="5" fill="#FACC15" filter="url(#subtleGlow)"/>
      <circle cx="0" cy="0" r="9" fill="none" stroke="#FACC15" stroke-width="1" stroke-opacity="0.4"/>
    </g>
    <g transform="translate(-130, 30)">
      <circle cx="0" cy="0" r="5" fill="#10B981" filter="url(#subtleGlow)"/>
      <circle cx="0" cy="0" r="9" fill="none" stroke="#10B981" stroke-width="1" stroke-opacity="0.4"/>
    </g>

  </g>

  <!-- ==================== CENTER HERO TYPOGRAPHY ==================== -->
  <g transform="translate(960, 620)">
    
    <!-- Main Project Name -->
    <text x="0" y="50" fill="url(#titleGoldGrad)" class="font-serif" font-size="78" font-weight="900" letter-spacing="-1" text-anchor="middle">AEGIS</text>

    <!-- Subtitle -->
    <text x="0" y="105" fill="#34D399" class="font-sans" font-size="28" font-weight="700" letter-spacing="0.5" text-anchor="middle">Autonomous Adaptive Portfolio Hedge Agent</text>

    <!-- Clean, Simple Tagline -->
    <text x="0" y="148" fill="#9CA3AF" class="font-sans" font-size="18" font-weight="400" text-anchor="middle">
      Intelligent closed-loop portfolio defense &amp; option collars powered by Nano Banana.
    </text>

    <!-- 3 Minimal Feature Badges -->
    <g transform="translate(0, 205)">
      <!-- Badge 1 -->
      <g transform="translate(-360, 0)">
        <rect x="0" y="0" width="220" height="40" rx="20" fill="#0A1F16" stroke="#10B981" stroke-width="1" stroke-opacity="0.5"/>
        <circle cx="20" cy="20" r="4" fill="#10B981"/>
        <text x="36" y="25" fill="#E2E8F0" class="font-mono" font-size="11.5" font-weight="600">Multi-Agent Options</text>
      </g>

      <!-- Badge 2 -->
      <g transform="translate(-110, 0)">
        <rect x="0" y="0" width="220" height="40" rx="20" fill="#0A1F16" stroke="#FACC15" stroke-width="1" stroke-opacity="0.5"/>
        <circle cx="20" cy="20" r="4" fill="#FACC15"/>
        <text x="36" y="25" fill="#FEF08A" class="font-mono" font-size="11.5" font-weight="600">Deterministic Risk Gate</text>
      </g>

      <!-- Badge 3 -->
      <g transform="translate(140, 0)">
        <rect x="0" y="0" width="220" height="40" rx="20" fill="#0A1F16" stroke="#0D9488" stroke-width="1" stroke-opacity="0.5"/>
        <circle cx="20" cy="20" r="4" fill="#0D9488"/>
        <text x="36" y="25" fill="#E2E8F0" class="font-mono" font-size="11.5" font-weight="600">Alpaca Paper Trading</text>
      </g>
    </g>

  </g>

  <!-- ==================== CLEAN MINIMAL FOOTER ==================== -->
  <g transform="translate(960, 1005)">
    <line x1="-700" y1="0" x2="700" y2="0" stroke="#10B981" stroke-width="1" stroke-opacity="0.2"/>
    <text x="0" y="32" fill="#6B7280" class="font-mono" font-size="12" letter-spacing="2" text-anchor="middle">
      PYTHON 3.11 • FASTAPI • POSTGRESQL • LANGGRAPH • ALPACA TRADING API
    </text>
  </g>

</svg>"""

os.makedirs("assets", exist_ok=True)

# Save clean SVG
with open("assets/cover_image.svg", "w", encoding="utf-8") as f:
    f.write(svg_content)

with open("assets/cover_image_nano_banana.svg", "w", encoding="utf-8") as f:
    f.write(svg_content)

print("Minimal SVG files written successfully.")

# Render clean PNG via Edge Headless
options = Options()
options.add_argument('--headless')
options.add_argument('--window-size=1920,1080')
options.add_argument('--hide-scrollbars')

driver = webdriver.Edge(options=options)
driver.set_window_size(1920, 1080)
svg_path = os.path.abspath('assets/cover_image.svg')
driver.get(f'file:///{svg_path}')
driver.save_screenshot('assets/cover_image.png')
driver.save_screenshot('assets/cover_image_nano_banana.png')

artifact_dir = r"C:\Users\LEGION\.gemini\antigravity\brain\b7f5ee5f-1cb3-4286-90ef-50bf09d35e04"
os.makedirs(artifact_dir, exist_ok=True)
driver.save_screenshot(os.path.join(artifact_dir, "cover_image_nano_banana.png"))
with open(os.path.join(artifact_dir, "cover_image_nano_banana.svg"), "w", encoding="utf-8") as f:
    f.write(svg_content)

driver.quit()
print("Clean minimal 16:9 PNG rendered and saved successfully in assets and artifacts!")
