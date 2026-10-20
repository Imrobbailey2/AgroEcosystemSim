import { defineConfig } from 'vite';

// Relative asset URLs so the build runs from inside a SCORM zip.
export default defineConfig({
  base: './',
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2022',
  },
});
