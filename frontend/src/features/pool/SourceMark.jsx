import { SocialIcon } from '../../components/SocialIcon';
import { sourceLabel, githubProfileUrl } from '../../lib/source';
import { cls } from '../../styles/cls';
import pool from '../../styles/pool.module.css';

import devtoLogo from '../../assets/devto_logo.webp';
export const SourceMark = ({ source, user }) => {
  if (source === 'devto') {
    const href = String(user.link || '').trim();
    const mark = <img className={cls(pool, "source-logo")} src={devtoLogo} alt="dev.to" />;
    if (!href) return mark;
    return (
      <a className={cls(pool, "source-link")} href={href} target="_blank" rel="noreferrer" title={href} aria-label={href}>
        {mark}
      </a>
    );
  }
  if (source === 'github') {
    const href = githubProfileUrl(user.github);
    if (!href) return null;
    return (
      <a className={cls(pool, "source-link source-github")} href={href} target="_blank" rel="noreferrer" title={href} aria-label={href}>
        <SocialIcon provider="github" size="lg" />
      </a>
    );
  }
  const label = sourceLabel(source);
  return <span className="source-label">{label}</span>;
};
