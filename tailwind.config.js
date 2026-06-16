/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/templates/**/*.html",
    "./app/static/src/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        app: {
          bg: 'var(--color-bg)',
          subtle: 'var(--color-bg-subtle)',
          inset: 'var(--color-bg-inset)',
          surface: 'var(--color-surface)',
          raised: 'var(--color-surface-raised)',
          muted: 'var(--color-surface-muted)',
          border: 'var(--color-border)',
          text: 'var(--color-text)',
          soft: 'var(--color-text-soft)',
        },
        primary: {
          DEFAULT: 'var(--color-primary)',
          hover: 'var(--color-primary-hover)',
          active: 'var(--color-primary-active)',
          text: 'var(--color-primary-text)',
        },
        success: {
          DEFAULT: 'var(--color-success)',
          bg: 'var(--color-success-bg)',
        },
        warning: {
          DEFAULT: 'var(--color-warning)',
          bg: 'var(--color-warning-bg)',
        },
        danger: {
          DEFAULT: 'var(--color-danger)',
          bg: 'var(--color-danger-bg)',
        },
        info: {
          DEFAULT: 'var(--color-info)',
          bg: 'var(--color-info-bg)',
        },
      },
    },
  },
  plugins: [],
};
