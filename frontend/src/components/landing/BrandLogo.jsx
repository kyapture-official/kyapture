export default function BrandLogo({ className = '' }) {
  return (
    <div className={`flex flex-col items-start leading-none ${className}`}>
      <svg
        viewBox="0 0 520 140"
        xmlns="http://www.w3.org/2000/svg"
        className="w-full h-auto"
        aria-label="Kyapture Photography"
      >
        <defs>
          <filter
            id="neon-glow"
            x="-20%"
            y="-20%"
            width="140%"
            height="140%"
          >
            <feGaussianBlur stdDeviation="2.2" result="blur1" />
            <feGaussianBlur stdDeviation="5" result="blur2" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="blur1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="slash-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="blur1" />
            <feGaussianBlur stdDeviation="7" result="blur2" />
            <feMerge>
              <feMergeNode in="blur2" />
              <feMergeNode in="blur1" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="slash-fill" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#00F0FF" />
            <stop offset="100%" stopColor="#14B8A6" />
          </linearGradient>
        </defs>

        <text
          x="0"
          y="100"
          fontFamily="'Inter', 'Helvetica Neue', Arial, sans-serif"
          fontSize="110"
          fontWeight="800"
          letterSpacing="6"
          fill="#0A0E1A"
          stroke="#00F0FF"
          strokeWidth="2"
          filter="url(#neon-glow)"
        >
          K<tspan dx="0">APTURE</tspan>
        </text>

        <g filter="url(#slash-glow)">
          <line
            x1="58"
            y1="115"
            x2="2"
            y2="-5"
            stroke="#00F0FF"
            strokeWidth="10"
            strokeLinecap="round"
          />
          <line
            x1="58"
            y1="115"
            x2="2"
            y2="-5"
            stroke="url(#slash-fill)"
            strokeWidth="6"
            strokeLinecap="round"
          />
        </g>

        <line
          x1="58"
          y1="115"
          x2="78"
          y2="115"
          stroke="#00F0FF"
          strokeWidth="10"
          strokeLinecap="round"
          filter="url(#slash-glow)"
        />
      </svg>

      <span className="mt-1.5 text-slate-500 tracking-[0.3em] text-[0.5rem] font-medium uppercase pl-[2px]">
        Photography
      </span>
    </div>
  );
}