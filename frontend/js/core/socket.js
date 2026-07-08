import { WS_BASE } from './config.js';

// WebSocket Manager - Real-time aloqa uchun
class WebSocketManager {
    constructor() {
        this.url = `${WS_BASE}/ws`;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.listeners = new Map();
        this.connected = false;
        this.heartbeatInterval = null;
    }
    
    // WebSocket ulanish
    connect() {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            console.log('WebSocket allaqachon ulangan');
            return;
        }
        
        const token = localStorage.getItem('access_token');
        const url = token ? `${this.url}?token=${token}` : this.url;
        
        this.socket = new WebSocket(url);
        
        this.socket.onopen = () => {
            console.log('WebSocket ulandi');
            this.connected = true;
            this.reconnectAttempts = 0;
            this.startHeartbeat();
            this.emit('connected', { timestamp: new Date().toISOString() });
        };
        
        this.socket.onmessage = (event) => {
            this.handleMessage(event.data);
        };
        
        this.socket.onerror = (error) => {
            console.error('WebSocket xatosi:', error);
            this.emit('error', error);
        };
        
        this.socket.onclose = () => {
            console.log('WebSocket uzildi');
            this.connected = false;
            this.stopHeartbeat();
            this.emit('disconnected', { timestamp: new Date().toISOString() });
            this.reconnect();
        };
    }
    
    // Xabarni qayta ishlash
    handleMessage(data) {
        try {
            const message = JSON.parse(data);
            
            // Heartbeat xabarini tekshirish
            if (message.type === 'ping') {
                this.send({ type: 'pong' });
                return;
            }
            
            // Tinglovchilarni chaqirish
            const listeners = this.listeners.get(message.type) || [];
            listeners.forEach(callback => {
                try {
                    callback(message.data || message);
                } catch (error) {
                    console.error('Listener xatosi:', error);
                }
            });
            
            // Umumiy message tinglovchilari
            const allListeners = this.listeners.get('*') || [];
            allListeners.forEach(callback => {
                try {
                    callback(message);
                } catch (error) {
                    console.error('Listener xatosi:', error);
                }
            });
            
        } catch (error) {
            console.error('Xabarni parse qilishda xatolik:', error, data);
        }
    }
    
    // Xabar yuborish
    send(data) {
        if (!this.connected || !this.socket) {
            console.warn('WebSocket ulanmagan');
            return false;
        }
        
        try {
            const message = typeof data === 'string' ? data : JSON.stringify(data);
            this.socket.send(message);
            return true;
        } catch (error) {
            console.error('Xabar yuborishda xatolik:', error);
            return false;
        }
    }
    
    // Tinglovchi qo'shish
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
        
        // Cleanup funksiyasini qaytarish
        return () => this.off(event, callback);
    }
    
    // Tinglovchini o'chirish
    off(event, callback) {
        if (!this.listeners.has(event)) return;
        
        const listeners = this.listeners.get(event);
        const index = listeners.indexOf(callback);
        
        if (index > -1) {
            listeners.splice(index, 1);
        }
        
        if (listeners.length === 0) {
            this.listeners.delete(event);
        }
    }
    
    // Event emit qilish (ichki ishlatish uchun)
    emit(event, data) {
        const listeners = this.listeners.get(event) || [];
        listeners.forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error('Emit xatosi:', error);
            }
        });
    }
    
    // Qayta ulanish
    reconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.log('Maksimal qayta ulanish soniga yetdi');
            this.emit('reconnect_failed', { attempts: this.reconnectAttempts });
            return;
        }
        
        this.reconnectAttempts++;
        
        console.log(`${this.reconnectDelay}ms dan keyin qayta ulanish (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            this.connect();
        }, this.reconnectDelay);
        
        // Keyingi urinish uchun kechikishni oshirish
        this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
    }
    
    // Heartbeat boshlash
    startHeartbeat() {
        this.stopHeartbeat();
        
        this.heartbeatInterval = setInterval(() => {
            if (this.connected) {
                this.send({ type: 'ping' });
            }
        }, 30000); // Har 30 sekundda
    }
    
    // Heartbeat to'xtatish
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
    
    // Ulanishni uzish
    disconnect() {
        this.stopHeartbeat();
        
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
        
        this.connected = false;
        this.reconnectAttempts = 0;
    }
    
    // Ulanish holatini tekshirish
    isConnected() {
        return this.connected && this.socket && this.socket.readyState === WebSocket.OPEN;
    }
    
    // Xonaga qo'shilish
    joinRoom(room) {
        this.send({
            type: 'join_room',
            room: room
        });
    }
    
    // Xonadan chiqish
    leaveRoom(room) {
        this.send({
            type: 'leave_room',
            room: room
        });
    }
}

export { WebSocketManager };