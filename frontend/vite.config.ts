import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
const apiPort=Number(process.env.KEDR_API_PORT||8710);
if(!Number.isInteger(apiPort)||apiPort<1024||apiPort>65535)throw new Error('Invalid local KEDR_API_PORT');
const api='http://127.0.0.1:'+apiPort;
export default defineConfig({plugins:[react()],server:{host:'127.0.0.1',port:5173,strictPort:true,proxy:{'/api':api}},preview:{host:'127.0.0.1',port:5173,proxy:{'/api':api}},build:{chunkSizeWarningLimit:1200}});
