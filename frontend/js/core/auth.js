import { API } from './api.js';
import { API_BASE } from './config.js';

// Auth Service - Autentifikatsiya uchun
class AuthService {
    constructor() {
        this.api = new API();
        this.user = null;
        this.loadUserFromStorage();
    }
    
    // LocalStorage dan foydalanuvchini yuklash
    loadUserFromStorage() {
        const userJson = localStorage.getItem('user');
        if (userJson) {
            try {
                this.user = JSON.parse(userJson);
            } catch (e) {
                this.user = null;
            }
        }
    }
    
    // Foydalanuvchini saqlash
    saveUserToStorage(user) {
        this.user = user;
        localStorage.setItem('user', JSON.stringify(user));
    }
    
    // Tizimga kirish
    async login(username, password) {
        try {
            const formData = new FormData();
            formData.append('username', username);
            formData.append('password', password);
            
            const response = await fetch(`${API_BASE}/auth/login`, {
                method: 'POST',
                body: formData
            });
            
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || 'Kirishda xatolik');
            }
            
            const data = await response.json();
            
            // Tokenlarni saqlash
            this.api.setToken(data.access_token);
            this.api.setRefreshToken(data.refresh_token);
            
            // Foydalanuvchi ma'lumotlarini olish
            const userResponse = await this.api.get('/auth/me');
            
            if (userResponse.success) {
                this.saveUserToStorage(userResponse.data);
            }
            
            return {
                success: true,
                user: this.user
            };
            
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // Ro'yxatdan o'tish
    async register(userData) {
        try {
            const response = await this.api.post('/auth/register', userData);
            
            if (response.success) {
                return {
                    success: true,
                    data: response.data
                };
            }
            
            throw new Error(response.error || 'Ro\'yxatdan o\'tishda xatolik');
            
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // Tizimdan chiqish
    async logout() {
        try {
            await this.api.post('/auth/logout');
        } catch (error) {
            console.error('Logout error:', error);
        } finally {
            this.api.clearTokens();
            this.user = null;
            localStorage.removeItem('user');
        }
    }
    
    // Parolni o'zgartirish
    async changePassword(oldPassword, newPassword) {
        try {
            const response = await this.api.post('/auth/change-password', {
                old_password: oldPassword,
                new_password: newPassword
            });
            
            return {
                success: response.success,
                message: response.data?.message || 'Parol o\'zgartirildi'
            };
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // Parolni tiklash so'rovi
    async forgotPassword(email) {
        try {
            const response = await this.api.post('/auth/forgot-password', { email });
            
            return {
                success: response.success,
                message: 'Parol tiklash havolasi emailga yuborildi'
            };
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // Parolni tiklash
    async resetPassword(token, newPassword) {
        try {
            const response = await this.api.post('/auth/reset-password', {
                token,
                new_password: newPassword
            });
            
            return {
                success: response.success,
                message: 'Parol muvaffaqiyatli o\'zgartirildi'
            };
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
    
    // Autentifikatsiya holatini tekshirish
    isAuthenticated() {
        return !!this.api.getToken() && !!this.user;
    }
    
    // Joriy foydalanuvchini olish
    getCurrentUser() {
        return this.user;
    }
    
    // Foydalanuvchi rolini tekshirish
    hasRole(role) {
        return this.user && (this.user.role?.name || this.user.role) === role;
    }
    
    // Foydalanuvchi ruxsatini tekshirish
    hasPermission(permission) {
        if (!this.user) return false;
        
        // Superuser hamma ruxsatga ega
        if (this.user.is_superuser) return true;
        
        // Role orqali ruxsatlarni tekshirish
        return this.user.permissions && this.user.permissions.includes(permission);
    }
    
    // Tokenni yangilash
    async refreshToken() {
        try {
            return await this.api.refreshAccessToken();
        } catch (error) {
            this.logout();
            throw error;
        }
    }
    
    // Foydalanuvchi profilini yangilash
    async updateProfile(userData) {
        try {
            const response = await this.api.patch('/users/me', userData);
            
            if (response.success) {
                this.saveUserToStorage({
                    ...this.user,
                    ...response.data
                });
            }
            
            return response;
        } catch (error) {
            return {
                success: false,
                error: error.message
            };
        }
    }
}

export { AuthService };