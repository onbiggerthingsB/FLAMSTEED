import { render, screen } from '@testing-library/svelte';
import App from '../../src/App.svelte';

test('app mounts and shows the title', () => {
  render(App);
  expect(screen.getByTestId('app-title')).toBeInTheDocument();
});
