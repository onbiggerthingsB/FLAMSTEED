import { mountEmbed } from './embed';

const target = document.querySelector<HTMLElement>('#wc-embed-frame');
const pathMatch = location.pathname.match(/^\/v1\/frame\/([a-z0-9][a-z0-9_-]{1,31})$/);
const query = new URLSearchParams(location.search);
const frameKey = query.get('k');
const tournament = query.get('tournament') ?? 'wc2026';
const requestedSurface = query.get('surface');
const surface = requestedSurface === 'schedule' ? 'schedule' : 'ladder';

if (!target || !pathMatch || !frameKey || !/^[a-z0-9]{2,16}$/.test(tournament)) {
  throw new Error('invalid publisher frame URL');
}

mountEmbed(target, {
  endpoint: location.origin,
  publisherId: pathMatch[1],
  tournament,
  surface,
  frameKey,
});
