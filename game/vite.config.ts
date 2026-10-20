/// <reference types="vitest/config" />
import { defineConfig } from 'vite';
import preact from '@preact/preset-vite';

// base: './' gives relative asset URLs, so the same build works on
// GitHub Pages (/AgroEcosystemSim/) and later inside a SCORM zip in Canvas.
export default defineConfig({
  base: './',
  plugins: [preact()],
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
  test: {
    environment: 'jsdom',
    include: ['tests/unit/**/*.test.{ts,tsx}'],
  },
});
