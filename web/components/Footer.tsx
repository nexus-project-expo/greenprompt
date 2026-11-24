import { TEAM } from "./team";

type IconProps = { className?: string };

function LinkedInIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className={className}>
      <rect width="24" height="24" rx="4" fill="#0a66c2" />
      <rect x="5" y="9.5" width="3" height="9.5" fill="#fff" />
      <circle cx="6.5" cy="6.3" r="1.8" fill="#fff" />
      <path d="M10.5 9.5h2.9v1.3c.5-.9 1.6-1.6 3.1-1.6 2.6 0 3.5 1.6 3.5 4.3V19h-3v-4.8c0-1.2-.3-2.2-1.5-2.2s-1.9.9-1.9 2.2V19h-3.1z" fill="#fff" />
    </svg>
  );
}

// The Gmail "M", as in PhishGuard's footer.
function GmailIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" className={className}>
      <path d="M2 6.5V18a1.5 1.5 0 0 0 1.5 1.5H6V10l6 4.5 6-4.5v9.5h2.5A1.5 1.5 0 0 0 22 18V6.5a2 2 0 0 0-3.2-1.6L12 10 5.2 4.9A2 2 0 0 0 2 6.5z" />
    </svg>
  );
}

function InstagramIcon({ className }: IconProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true" className={className}>
      <rect x="2" y="2" width="20" height="20" rx="5" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="17.5" cy="6.5" r="1" fill="currentColor" stroke="none" />
    </svg>
  );
}

function Social({ href, label, Icon }: { href: string; label: string; Icon: (p: IconProps) => React.ReactElement }) {
  if (!href) {
    return (
      <span className="social off" title={`${label}: coming soon`} aria-hidden="true">
        <Icon className="social-icon" />
      </span>
    );
  }
  return (
    <a className="social" href={href} target={href.startsWith("mailto:") ? undefined : "_blank"} rel="noopener noreferrer" aria-label={label}>
      <Icon className="social-icon" />
    </a>
  );
}

export default function Footer() {
  return (
    <footer className="site-footer">
      <section className="devs-row" aria-labelledby="contact-devs">
        <h2 id="contact-devs">Contact the devs</h2>
        <ul className="devs">
          {TEAM.map((dev) => (
            <li key={dev.name}>
              {dev.linkedin ? (
                <a className="dev-name" href={dev.linkedin} target="_blank" rel="noopener noreferrer">
                  {dev.name}
                  <LinkedInIcon className="dev-li" />
                </a>
              ) : (
                <span className="dev-name">{dev.name}</span>
              )}
              <Social href={dev.email && `mailto:${dev.email}`} label={`Email ${dev.name}`} Icon={GmailIcon} />
              <Social href={dev.instagram} label={`${dev.name} on Instagram`} Icon={InstagramIcon} />
            </li>
          ))}
        </ul>
      </section>
      <p className="footer-copy">© {new Date().getFullYear()} GreenPrompt, Team Undervolt, NMAM Institute of Technology</p>
    </footer>
  );
}
