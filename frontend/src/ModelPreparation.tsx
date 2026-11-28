import { useEffect, useState } from "react";
import { apiConfig } from "./api";

export default function ModelPreparation() {
  const [message,setMessage]=useState("");
  useEffect(() => {
    if (!apiConfig.enabled) return;
    let disposed=false;
    const refresh=async () => {
      try {
        const response=await fetch(`${apiConfig.base}/runtime/generation-ready?language=en`);
        if (response.ok) {
          const state=await response.json();
          if(!disposed) setMessage(state.ready ? "" : state.message);
        }
      } catch { /* The document and question actions provide recovery messages. */ }
    };
    void refresh();const timer=setInterval(() => void refresh(),1500);
    return () => {disposed=true;clearInterval(timer);};
  },[]);
  return message ? <div role="status" className="generation-preparation">{message}</div> : null;
}
