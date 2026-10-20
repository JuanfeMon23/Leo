/** Estado del aviso de inactividad (lo maneja el plugin de leo-client). */
export function useLeoIdle() {
  const state = useState('leo-idle', () => ({ warning: false, deadline: 0 }))
  const { $leo } = useNuxtApp()
  return {
    state,
    stayConnected: () => $leo.idle.stayConnected()
  }
}
