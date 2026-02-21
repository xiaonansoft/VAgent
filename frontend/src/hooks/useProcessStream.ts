import { useState, useEffect, useRef } from 'react';

export interface SensorStatus {
  is_valid: boolean;
  raw_value: number | null;
  estimated_value: number | null;
  confidence: number;
  correction_source: string;
}

export interface ProcessData {
  process_time?: number;
  temperature?: {
    value: number;
    status: SensorStatus;
    ts: string;
  };
  chemistry?: {
    si: number;
    v: number;
    c: number;
  };
  lance_height?: {
    value: number;
    ts: string;
  };
  model_params?: {
    heat_efficiency: number;
    reaction_rate_mod: number;
  };
  is_emergency_stop?: boolean;
  latest_sample?: {
    time: number;
    temp: number;
    C: number;
    V: number;
  };
}

export function useProcessStream() {
  const [data, setData] = useState<ProcessData>({});
  const [isConnected, setIsConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const connect = () => {
      console.log('Connecting to SSE stream...');
      const es = new EventSource('/api/stream');
      eventSourceRef.current = es;

      es.onopen = () => {
        console.log('SSE connection opened');
        setIsConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          // Assuming payload is the full state update or partial
          // Since our simulator sends full state snapshot every second, we can just replace or merge
          // But to be safe with partial updates, we merge
          setData(prev => ({ ...prev, ...payload }));
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };

      es.onerror = (error) => {
        console.error('SSE connection error:', error);
        setIsConnected(false);
        es.close();
        // Simple reconnect logic
        setTimeout(connect, 3000);
      };
    };

    connect();

    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return { data, isConnected };
}
