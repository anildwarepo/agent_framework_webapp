import './App.css'
import { Toaster } from "@/components/ui/sonner";
import LandingPage from './Landing.tsx';
import ChatUI from './ChatUI.tsx';

function App() {
  

  return (
   
    <>
      <LandingPage />
      <Toaster richColors position="top-right" />
      
    </>
    
  )
}

export default App
