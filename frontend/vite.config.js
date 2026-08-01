import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    proxy: {
      '/simulate':            'http://localhost:8000',
      '/preview-dss':         'http://localhost:8000',
      '/health':              'http://localhost:8000',
      '/export-pdf':          'http://localhost:8000',
      '/fault-study':         'http://localhost:8000',
      '/simulate-timeseries': 'http://localhost:8000',

      '/scada/health':        'http://localhost:8000',
      '/scada/state':         'http://localhost:8000',
      '/scada/alarms':        'http://localhost:8000',
      '/scada/events':        'http://localhost:8000',
      '/scada/history':       'http://localhost:8000',

      '/scada/ws': {
        target:       'ws://localhost:8000',
        ws:           true,
        changeOrigin: true,
      },
    },
  },
})
