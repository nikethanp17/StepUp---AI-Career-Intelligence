import { useState, useRef, useCallback } from 'react';

const API_BASE = 'http://127.0.0.1:8000';

// ─── Utility: fetch wrapper ───────────────────────────────────────────────────
async function apiFetch(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} on ${path}`);
  return res.json();
}

// ─── Extract meaningful tech keywords from raw JD text ───────────────────────
// Splits on non-alphanumeric boundaries, strips English stop-words and short
// filler words, and deduplicates — so only real skill tokens reach the API.
const STOP_WORDS = new Set([
  'a','an','the','and','or','but','in','on','at','to','for','of','with','by',
  'from','as','is','are','was','were','be','been','being','have','has','had',
  'do','does','did','will','would','could','should','may','might','can','shall',
  'not','no','nor','so','yet','both','either','neither','than','then','that',
  'this','these','those','it','its','we','our','you','your','they','their',
  'he','she','his','her','who','whom','which','what','when','where','how','why',
  'if','unless','until','while','although','though','because','since','after',
  'before','about','above','across','against','along','among','around','behind',
  'below','between','during','except','into','near','off','over','past',
  'through','under','up','upon','within','without','per','via',
  // generic HR/resume filler words
  'role','position','team','work','working','experience','strong','good',
  'ability','skills','knowledge','understanding','including','such','like',
  'also','well','using','use','build','building','develop','developing',
  'ensure','must','need','required','preferred','plus','bonus','candidate',
  'join','help','make','other','across','own','new','job','responsible',
  'years','year','least','more','most','all','any','some','many','much',
]);

function extractTechKeywords(text) {
  // Split on whitespace and common punctuation
  const tokens = text.split(/[\s,;/|\-().\[\]"]+/);
  const seen = new Set();
  const keywords = [];

  for (const raw of tokens) {
    // Strip trailing punctuation / version numbers like "v2", "3.x"
    const token = raw.replace(/[^a-zA-Z0-9#+.]/g, '').trim();

    // Keep if: 2+ chars, not a pure number, not a stop-word
    if (
      token.length >= 2 &&
      !/^\d+(\.\d+)?$/.test(token) &&
      !STOP_WORDS.has(token.toLowerCase()) &&
      !seen.has(token.toLowerCase())
    ) {
      seen.add(token.toLowerCase());
      keywords.push(token);
    }
  }

  return keywords;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

/** Animated SVG score ring */
function ScoreRing({ score }) {
  const r = 54;
  const circumference = 2 * Math.PI * r;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 70 ? '#10b981' : score >= 45 ? '#f59e0b' : '#ef4444';

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width="140" height="140" viewBox="0 0 140 140" className="drop-shadow-[0_0_20px_rgba(124,58,237,0.5)]">
        <circle cx="70" cy="70" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
        <circle
          cx="70" cy="70" r={r}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 70 70)"
          style={{ transition: 'stroke-dashoffset 1.4s cubic-bezier(0.4,0,0.2,1)', filter: `drop-shadow(0 0 8px ${color})` }}
        />
        <text x="70" y="65" textAnchor="middle" fill="white" fontSize="26" fontWeight="800" fontFamily="Inter">
          {score}%
        </text>
        <text x="70" y="85" textAnchor="middle" fill="rgba(255,255,255,0.5)" fontSize="11" fontFamily="Inter">
          Match Score
        </text>
      </svg>
      <p className="text-sm font-medium" style={{ color }}>
        {score >= 70 ? '🚀 Strong Match' : score >= 45 ? '⚡ Moderate Match' : '🔧 Needs Work'}
      </p>
    </div>
  );
}

/** Step indicator shown during loading */
function StepIndicator({ steps, current }) {
  return (
    <div className="flex flex-col gap-3 w-full max-w-xs mx-auto">
      {steps.map((step, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <div key={i} className="flex items-center gap-3">
            <div className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-all duration-500
              ${done ? 'bg-emerald-500 text-white shadow-[0_0_12px_rgba(16,185,129,0.6)]' :
                active ? 'bg-violet-600 text-white shadow-[0_0_12px_rgba(124,58,237,0.7)]' :
                'bg-white/10 text-white/30'}`}>
              {done ? '✓' : i + 1}
            </div>
            <span className={`text-sm font-medium transition-colors duration-300
              ${done ? 'text-emerald-400' : active ? 'text-violet-300' : 'text-white/30'}`}>
              {step}
            </span>
            {active && (
              <span className="ml-auto flex gap-1">
                {[0, 1, 2].map(d => (
                  <span key={d} className="pulse-dot w-1.5 h-1.5 rounded-full bg-violet-400"
                    style={{ animationDelay: `${d * 0.2}s` }} />
                ))}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Skill pill tag */
function Pill({ label, delay = 0, variant = 'missing' }) {
  const styles = {
    missing: 'bg-rose-500/15 text-rose-300 border border-rose-500/30',
    tech:    'bg-indigo-500/15 text-indigo-300 border border-indigo-500/30',
    resume:  'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30',
  };
  return (
    <span
      className={`pill-animate inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold ${styles[variant]}`}
      style={{ animationDelay: `${delay}ms` }}>
      {label}
    </span>
  );
}

/** Copy-to-clipboard box */
function CopyBox({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group">
      <div className="bg-white/[0.04] border border-white/10 rounded-xl p-4 pr-16 text-sm text-slate-300 leading-relaxed font-mono">
        {text}
      </div>
      <button
        onClick={copy}
        className="absolute top-3 right-3 px-2.5 py-1.5 rounded-lg text-xs font-medium bg-violet-600/80 hover:bg-violet-600 text-white transition-all duration-200 opacity-0 group-hover:opacity-100">
        {copied ? '✓ Copied' : 'Copy'}
      </button>
    </div>
  );
}

/** Reusable styled textarea */
function Textarea({ label, id, value, onChange, placeholder, rows = 5 }) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-semibold text-slate-300">{label}</label>
      <textarea
        id={id}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
        className="w-full bg-white/[0.04] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600
          focus:outline-none focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/20
          resize-none transition-all duration-200 leading-relaxed"
      />
    </div>
  );
}

// ─── File icon by extension ───────────────────────────────────────────────────
function FileTypeIcon({ filename }) {
  const ext = filename?.split('.').pop()?.toLowerCase();
  const icons = { pdf: '📄', docx: '📝', doc: '📝', txt: '📃' };
  return <span className="text-2xl">{icons[ext] ?? '📎'}</span>;
}

// ─── Drag-and-drop / file upload zone ────────────────────────────────────────
function ResumeUploadZone({ file, setFile, extractedText, setExtractedText, uploading, setUploading }) {
  const [dragOver, setDragOver]         = useState(false);
  const [previewOpen, setPreviewOpen]   = useState(false);
  const [showFallback, setShowFallback] = useState(false);
  const [fallbackText, setFallbackText] = useState('');
  const fileInputRef = useRef(null);

  // Upload a File object to the backend
  const uploadFile = useCallback(async (f) => {
    setUploading(true);
    setExtractedText(null);
    try {
      const formData = new FormData();
      formData.append('file', f);
      const res = await fetch(`${API_BASE}/api/upload-resume`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (data.status === 'error') throw new Error(data.message);
      setExtractedText(data.extracted_text);
      setFile(f);
    } catch (err) {
      alert(`Upload failed: ${err.message}`);
      setFile(null);
    } finally {
      setUploading(false);
    }
  }, [setFile, setExtractedText, setUploading]);

  const handleFileChange = (e) => {
    const f = e.target.files?.[0];
    if (f) uploadFile(f);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) uploadFile(f);
  };

  const handleRemove = () => {
    setFile(null);
    setExtractedText(null);
    setPreviewOpen(false);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // ── Uploaded state ──────────────────────────────────────────────────────────
  if (file && extractedText !== null) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-semibold text-slate-300">📄 Resume</label>
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
            ✓ Uploaded
          </span>
        </div>

        {/* File card */}
        <div className="bg-white/[0.04] border border-emerald-500/30 rounded-xl p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/15 border border-emerald-500/20 flex items-center justify-center shrink-0">
            <FileTypeIcon filename={file.name} />
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-semibold text-white truncate">{file.name}</p>
            <p className="text-xs text-slate-500 mt-0.5">{(file.size / 1024).toFixed(1)} KB · Text extracted</p>
          </div>
          <button
            onClick={handleRemove}
            className="px-3 py-1.5 rounded-lg text-xs font-semibold text-rose-400 border border-rose-500/20 hover:bg-rose-500/10 transition-all duration-200 shrink-0">
            Remove
          </button>
        </div>

        {/* Collapsible preview */}
        <div className="rounded-xl border border-white/[0.06] overflow-hidden">
          <button
            onClick={() => setPreviewOpen(p => !p)}
            className="w-full flex items-center justify-between px-4 py-2.5 bg-white/[0.02] text-xs font-medium text-slate-500 hover:text-slate-300 transition-colors">
            <span>Extracted text preview</span>
            <span className="text-slate-600">{previewOpen ? '▲ Collapse' : '▼ Expand'}</span>
          </button>
          {previewOpen && (
            <div className="px-4 py-3 bg-white/[0.02] text-xs text-slate-400 font-mono leading-relaxed border-t border-white/[0.05] max-h-32 overflow-y-auto">
              {extractedText.slice(0, 300)}
              {extractedText.length > 300 && <span className="text-slate-600"> …({extractedText.length} chars total)</span>}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Upload / drag-drop state ────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label className="text-sm font-semibold text-slate-300">📄 Resume</label>
        <div className="flex items-center gap-2">
          <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-500/15 text-violet-400 border border-violet-500/20">
            PDF / DOCX / TXT
          </span>
        </div>
      </div>

      {/* Drop zone */}
      <div
        id="resume-dropzone"
        onDragOver={e => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => !uploading && fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed cursor-pointer transition-all duration-200 py-10 px-4
          ${dragOver
            ? 'border-violet-400 bg-violet-500/10 scale-[1.01]'
            : 'border-white/15 bg-white/[0.02] hover:border-violet-500/40 hover:bg-violet-500/5'
          } ${uploading ? 'pointer-events-none opacity-70' : ''}`}>

        {uploading ? (
          <>
            <svg className="animate-spin w-8 h-8 text-violet-400" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/>
            </svg>
            <p className="text-sm font-medium text-violet-300">Uploading & extracting text…</p>
          </>
        ) : (
          <>
            <div className={`w-14 h-14 rounded-2xl flex items-center justify-center transition-all duration-200
              ${dragOver ? 'bg-violet-500/25 shadow-[0_0_20px_rgba(124,58,237,0.4)]' : 'bg-white/[0.05]'}`}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none"
                stroke={dragOver ? '#a78bfa' : 'rgba(255,255,255,0.35)'} strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                <polyline points="17 8 12 3 7 8"/>
                <line x1="12" y1="3" x2="12" y2="15"/>
              </svg>
            </div>
            <div className="text-center">
              <p className={`text-sm font-semibold transition-colors ${dragOver ? 'text-violet-300' : 'text-slate-300'}`}>
                {dragOver ? 'Drop your resume here' : 'Drag & drop your resume'}
              </p>
              <p className="text-xs text-slate-600 mt-1">or click to browse · PDF, DOCX, TXT supported</p>
            </div>
          </>
        )}

        <input
          ref={fileInputRef}
          id="resume-file-input"
          type="file"
          accept=".pdf,.docx,.doc,.txt"
          onChange={handleFileChange}
          className="hidden"
        />
      </div>

      {/* Fallback toggle */}
      <button
        type="button"
        onClick={() => setShowFallback(p => !p)}
        className="text-xs text-slate-600 hover:text-slate-400 underline underline-offset-2 self-start transition-colors mt-1">
        {showFallback ? '▲ Hide text input' : '▼ Prefer to paste text instead?'}
      </button>

      {showFallback && (
        <div className="fade-up">
          <Textarea
            id="resume-fallback-textarea"
            label=""
            value={fallbackText}
            onChange={(v) => {
              setFallbackText(v);
              // Treat typed text as extracted text so the pipeline uses it
              setExtractedText(v || null);
            }}
            placeholder="Paste your resume text here as a fallback…"
            rows={6}
          />
        </div>
      )}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  // Resume state
  const [resumeFile, setResumeFile]       = useState(null);
  const [extractedText, setExtractedText] = useState(null);
  const [uploading, setUploading]         = useState(false);

  // Other form fields
  const [jdText, setJdText]         = useState('');
  const [targetRole, setTargetRole] = useState('');

  // Async / results state
  const [loading, setLoading]         = useState(false);
  const [currentStep, setCurrentStep] = useState(-1);
  const [error, setError]             = useState(null);
  const [results, setResults]         = useState(null);

  const resultsRef = useRef(null);

  const STEPS = [
    'Extracting skills from resume…',
    'Semantic skill matching…',
    'Generating AI blueprint…',
  ];

  const handleAnalyze = async () => {
    const resumeText = extractedText?.trim();

    if (!resumeText) {
      setError('Please upload a resume file (or paste your resume text) before analyzing.');
      return;
    }
    if (!jdText.trim()) {
      setError('Please paste the job description.');
      return;
    }
    if (!targetRole.trim()) {
      setError('Please enter a target role.');
      return;
    }

    setError(null);
    setResults(null);
    setLoading(true);

    try {
      // ── Step A: Extract Skills ──────────────────────────────────────────────
      setCurrentStep(0);
      const entityData = await apiFetch('/api/extract-entities', { text: resumeText });
      const skills = entityData.skills_identified ?? [];

           // ── Step B: Match Skills ────────────────────────────────────────────────
      setCurrentStep(1);
      const matchData = await apiFetch('/api/match-skills', {
        resume_skills: skills,
        jd_text: jdText, // <-- SEND THE RAW JD TEXT HERE
      });
      const { semantic_match_score, missing_skills } = matchData;

      // ── Step C: Generate Blueprint ──────────────────────────────────────────
      setCurrentStep(2);
      const bpData = await apiFetch('/api/generate-blueprint', {
        missing_skills,
        target_role: targetRole,
      });
      const blueprint = bpData.blueprint;

      setResults({ score: semantic_match_score, missingSkills: missing_skills, blueprint });
      setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 100);

    } catch (err) {
      console.error(err);
      setError(`Backend error: ${err.message}. Make sure the FastAPI server is running at ${API_BASE}.`);
    } finally {
      setLoading(false);
      setCurrentStep(-1);
    }
  };

  const handleReset = () => {
    setResults(null);
    setResumeFile(null);
    setExtractedText(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="bg-animated min-h-screen">

      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-50 border-b border-white/[0.06] backdrop-blur-xl bg-black/30">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shadow-[0_0_16px_rgba(124,58,237,0.5)]">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
                <polyline points="17 6 23 6 23 12" />
              </svg>
            </div>
            <span className="text-lg font-bold bg-gradient-to-r from-violet-400 to-indigo-400 bg-clip-text text-transparent">
              StepUp
            </span>
            <span className="hidden sm:inline text-xs font-medium text-slate-500 ml-1">AI Career Intelligence</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-500/15 text-emerald-400 border border-emerald-500/20">
              ● Backend Live
            </span>
          </div>
        </div>
      </header>

      {/* ── Hero ───────────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pt-16 pb-10 text-center">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-400 pulse-dot" />
          Powered by spaCy · Sentence-Transformers · Gemini 2.5 Flash
        </div>
        <h1 className="text-4xl sm:text-5xl font-extrabold text-white leading-tight mb-4">
          Land your dream job with{' '}
          <span className="bg-gradient-to-r from-violet-400 via-purple-400 to-indigo-400 bg-clip-text text-transparent">
            AI-powered
          </span>{' '}
          insights
        </h1>
        <p className="text-slate-400 text-lg max-w-2xl mx-auto">
          Upload your resume or paste your text. StepUp's three-model AI pipeline will analyze your fit,
          find skill gaps, and generate a personalized project blueprint — in seconds.
        </p>
      </section>

      {/* ── Input Form ─────────────────────────────────────────────────────── */}
      <section className="max-w-6xl mx-auto px-6 pb-16">
        <div className="gradient-border p-6 sm:p-8">

          {/* Error banner */}
          {error && (
            <div className="mb-6 flex items-start gap-3 bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 text-rose-300 text-sm">
              <span className="text-lg">⚠️</span>
              <p>{error}</p>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left col — Resume upload */}
            <ResumeUploadZone
              file={resumeFile}
              setFile={setResumeFile}
              extractedText={extractedText}
              setExtractedText={setExtractedText}
              uploading={uploading}
              setUploading={setUploading}
            />

            {/* Right col — JD + Role */}
            <div className="flex flex-col gap-6">
              <Textarea
                id="jd-input"
                label="💼 Job Description"
                value={jdText}
                onChange={setJdText}
                placeholder="Paste the full job description here…&#10;&#10;Include responsibilities, required skills, and qualifications."
                rows={7}
              />
              <div className="flex flex-col gap-2">
                <label htmlFor="target-role" className="text-sm font-semibold text-slate-300">🎯 Target Role</label>
                <input
                  id="target-role"
                  type="text"
                  value={targetRole}
                  onChange={e => setTargetRole(e.target.value)}
                  placeholder="e.g. Backend Developer, ML Engineer, Frontend Developer…"
                  className="w-full bg-white/[0.04] border border-white/10 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-600
                    focus:outline-none focus:border-violet-500/60 focus:ring-2 focus:ring-violet-500/20
                    transition-all duration-200"
                />
              </div>
            </div>
          </div>

          {/* CTA Button */}
          <div className="mt-8 flex justify-center">
            <button
              id="analyze-btn"
              onClick={handleAnalyze}
              disabled={loading || uploading}
              className="group relative px-8 py-4 rounded-2xl font-bold text-base text-white
                bg-gradient-to-r from-violet-600 to-indigo-600
                shadow-[0_0_30px_rgba(124,58,237,0.4)]
                hover:shadow-[0_0_50px_rgba(124,58,237,0.6)]
                hover:scale-[1.02] active:scale-[0.98]
                disabled:opacity-60 disabled:cursor-not-allowed disabled:hover:scale-100
                transition-all duration-200">
              {loading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="white" strokeWidth="3"/>
                    <path className="opacity-75" fill="white" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/>
                  </svg>
                  Analyzing…
                </span>
              ) : uploading ? (
                <span className="flex items-center gap-2">
                  <svg className="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="white" strokeWidth="3"/>
                    <path className="opacity-75" fill="white" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/>
                  </svg>
                  Uploading file…
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  ✨ Analyze &amp; Generate Blueprint
                  <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                    <path d="M5 12h14M12 5l7 7-7 7"/>
                  </svg>
                </span>
              )}
            </button>
          </div>
        </div>

        {/* ── Loading State ─────────────────────────────────────────────────── */}
        {loading && (
          <div className="mt-8 glass-card p-8 flex flex-col items-center gap-6 fade-up">
            <div className="w-14 h-14 rounded-2xl bg-violet-600/20 border border-violet-500/30 flex items-center justify-center shadow-[0_0_20px_rgba(124,58,237,0.3)]">
              <svg className="animate-spin w-7 h-7 text-violet-400" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3"/>
                <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.4 0 0 5.4 0 12h4z"/>
              </svg>
            </div>
            <div className="text-center">
              <p className="font-semibold text-white text-lg">Running AI Pipeline</p>
              <p className="text-slate-500 text-sm mt-1">Three ML models working in sequence…</p>
            </div>
            <StepIndicator steps={STEPS} current={currentStep} />
          </div>
        )}

        {/* ── Results Dashboard ─────────────────────────────────────────────── */}
        {results && !loading && (
          <div ref={resultsRef} className="mt-10 flex flex-col gap-6">

            {/* Row 1: Score + Missing Skills */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

              {/* Score Card */}
              <div className="glass-card p-6 flex flex-col items-center gap-4 fade-up">
                <div className="w-full flex items-center justify-between mb-2">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">Fit Score</h2>
                  <span className="text-xs font-medium text-slate-600">Semantic Similarity</span>
                </div>
                <ScoreRing score={Math.round(results.score)} />
                <p className="text-xs text-slate-600 text-center">
                  Based on semantic embedding comparison via Sentence-Transformers
                </p>
              </div>

              {/* Missing Skills */}
              <div className="glass-card p-6 flex flex-col gap-4 fade-up" style={{ animationDelay: '100ms' }}>
                <div className="flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-slate-400 uppercase tracking-widest">Skill Gaps</h2>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/20">
                    {results.missingSkills.length} missing
                  </span>
                </div>
                {results.missingSkills.length === 0 ? (
                  <div className="flex-1 flex flex-col items-center justify-center gap-2 text-emerald-400">
                    <span className="text-3xl">🎉</span>
                    <p className="font-semibold">No significant skill gaps!</p>
                    <p className="text-xs text-slate-500">Your resume matches the job description well.</p>
                  </div>
                ) : (
                  <div className="flex flex-wrap gap-2 content-start">
                    {results.missingSkills.map((skill, i) => (
                      <Pill key={skill} label={skill} delay={i * 50} variant="missing" />
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Row 2: Blueprint Card */}
            {results.blueprint && (
              <div className="gradient-border p-6 sm:p-8 fade-up" style={{ animationDelay: '200ms' }}>
                <div className="flex items-start gap-4 mb-6">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-violet-600 to-indigo-600 flex items-center justify-center shrink-0 shadow-[0_0_20px_rgba(124,58,237,0.4)]">
                    <span className="text-xl">🧩</span>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-violet-400 uppercase tracking-widest mb-1">
                      AI-Generated Project Blueprint
                    </p>
                    <h2 className="text-2xl font-extrabold text-white leading-tight">
                      {results.blueprint.project_name}
                    </h2>
                  </div>
                </div>

                <p className="text-slate-300 text-sm leading-relaxed mb-6 ml-16">
                  {results.blueprint.description}
                </p>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  {/* Core Features */}
                  <div>
                    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                      <span className="w-4 h-4 rounded bg-violet-500/20 inline-flex items-center justify-center text-violet-400">✦</span>
                      Core Features
                    </h3>
                    <ul className="flex flex-col gap-2">
                      {(results.blueprint.core_features ?? []).map((f, i) => (
                        <li key={i} className="flex items-start gap-3 text-sm text-slate-300 pill-animate"
                          style={{ animationDelay: `${300 + i * 60}ms` }}>
                          <span className="w-5 h-5 rounded-full bg-violet-600/20 border border-violet-500/30 flex items-center justify-center text-violet-400 text-xs shrink-0 mt-0.5">
                            {i + 1}
                          </span>
                          {f}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Tech Stack */}
                  <div>
                    <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                      <span className="w-4 h-4 rounded bg-indigo-500/20 inline-flex items-center justify-center text-indigo-400">⚙</span>
                      Tech Stack
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {(results.blueprint.tech_stack ?? []).map((tech, i) => (
                        <Pill key={tech} label={tech} delay={300 + i * 50} variant="tech" />
                      ))}
                    </div>
                  </div>
                </div>

                {/* Resume Bullet Point */}
                <div className="mt-6">
                  <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-widest mb-3 flex items-center gap-2">
                    <span className="w-4 h-4 rounded bg-emerald-500/20 inline-flex items-center justify-center text-emerald-400">✎</span>
                    Add to Your Resume
                  </h3>
                  <CopyBox text={results.blueprint.resume_bullet_point} />
                </div>

                <p className="mt-4 text-xs text-slate-600 text-center">
                  Generated by Gemini 2.5 Flash · Build this over a weekend to close your skill gaps 🚀
                </p>
              </div>
            )}

            {/* Re-analyze button */}
            <div className="flex justify-center fade-up" style={{ animationDelay: '300ms' }}>
              <button
                id="re-analyze-btn"
                onClick={handleReset}
                className="px-6 py-3 rounded-xl text-sm font-semibold text-slate-400 border border-white/10 hover:border-violet-500/40 hover:text-violet-300 transition-all duration-200">
                ← Analyze Another Role
              </button>
            </div>
          </div>
        )}
      </section>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <footer className="border-t border-white/[0.04] py-8 text-center text-xs text-slate-700">
        <p>StepUp · AI Career Intelligence Platform · Built with React + Vite + Tailwind CSS</p>
      </footer>
    </div>
  );
}
