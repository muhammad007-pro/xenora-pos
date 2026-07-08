import { API } from '../core/api.js';
import { showToast } from '../ui/toast.js';
import { Modal } from '../ui/modal.js';

class RecipesModule {
    constructor() {
        this.api = new API();
        this.modal = new Modal('recipeModal');
        this.recipes = [];
        this.products = [];
        this.ingredients = [];
        this.editingId = null;
        
        this.init();
    }
    
    async init() {
        await this.loadData();
        this.setupEventListeners();
        this.renderRecipes();
    }
    
    setupEventListeners() {
        document.getElementById('addRecipeBtn').addEventListener('click', () => this.openModal());
        document.getElementById('saveRecipeBtn').addEventListener('click', () => this.saveRecipe());
        document.getElementById('addIngredientBtn').addEventListener('click', () => this.addIngredientRow());
        document.getElementById('searchInput').addEventListener('input', () => this.filterRecipes());
        document.getElementById('categoryFilter').addEventListener('change', () => this.filterRecipes());
        
        document.querySelectorAll('.modal-close').forEach(btn => {
            btn.addEventListener('click', () => this.modal.close());
        });
    }
    
    async loadData() {
        try {
            // Mahsulotlarni yuklash
            const productsRes = await this.api.get('/products/all');
            this.products = productsRes.data || [];
            
            // Ingredientlar uchun mahsulotlar
            const ingredientsRes = await this.api.get('/inventory');
            this.ingredients = ingredientsRes.data?.items || [];
            
            // Retseptlarni yuklash
            const recipesRes = await this.api.get('/recipes');
            this.recipes = recipesRes.data?.items || [];
            
            this.populateProductSelect();
            this.populateCategoryFilter();
        } catch (error) {
            console.error('Ma\'lumotlarni yuklashda xatolik:', error);
            showToast('Ma\'lumotlarni yuklashda xatolik', 'error');
        }
    }
    
    populateProductSelect() {
        const select = document.getElementById('productSelect');
        select.innerHTML = '<option value="">Mahsulot tanlang</option>';
        
        // Retsepti bo'lmagan mahsulotlar
        const productsWithoutRecipe = this.products.filter(p => 
            !this.recipes.find(r => r.product_id === p.id)
        );
        
        productsWithoutRecipe.forEach(p => {
            const option = document.createElement('option');
            option.value = p.id;
            option.textContent = `${p.name} - ${p.category?.name || ''}`;
            select.appendChild(option);
        });
    }
    
    populateCategoryFilter() {
        const select = document.getElementById('categoryFilter');
        const categories = [...new Set(this.products.map(p => p.category?.name).filter(Boolean))];
        
        categories.forEach(cat => {
            const option = document.createElement('option');
            option.value = cat;
            option.textContent = cat;
            select.appendChild(option);
        });
    }
    
    renderRecipes() {
        const grid = document.getElementById('recipesGrid');
        
        if (this.recipes.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1/-1; text-align: center; padding: 60px;">
                    <h3>📋 Retseptlar mavjud emas</h3>
                    <p>Yangi retsept qo'shish uchun "Yangi retsept" tugmasini bosing</p>
                </div>
            `;
            return;
        }
        
        grid.innerHTML = this.recipes.map(recipe => this.createRecipeCard(recipe)).join('');
        
        // Action tugmalariga event listener qo'shish
        grid.querySelectorAll('.edit-recipe').forEach(btn => {
            btn.addEventListener('click', () => this.editRecipe(btn.dataset.id));
        });
        
        grid.querySelectorAll('.delete-recipe').forEach(btn => {
            btn.addEventListener('click', () => this.deleteRecipe(btn.dataset.id));
        });
    }
    
    createRecipeCard(recipe) {
        const product = this.products.find(p => p.id === recipe.product_id);
        const ingredients = recipe.items || [];
        
        return `
            <div class="recipe-card glass" data-id="${recipe.id}">
                <div class="recipe-header">
                    <h3 class="recipe-title">${recipe.name || product?.name || 'Retsept'}</h3>
                    <span class="recipe-time">⏱️ ${recipe.preparation_time} daq</span>
                </div>
                <p class="recipe-description">${recipe.description || ''}</p>
                <div class="ingredients-preview">
                    <strong>📝 Ingredientlar:</strong>
                    ${ingredients.slice(0, 3).map(i => `
                        <div class="ingredient-item">
                            <span class="ingredient-name">${i.ingredient_name}</span>
                            <span class="ingredient-quantity">${i.quantity} ${i.unit}</span>
                        </div>
                    `).join('')}
                    ${ingredients.length > 3 ? `<div class="ingredient-item">+${ingredients.length - 3} ta...</div>` : ''}
                </div>
                <div class="recipe-actions">
                    <button class="btn btn-outline btn-sm edit-recipe" data-id="${recipe.id}">✏️ Tahrirlash</button>
                    <button class="btn btn-outline btn-sm delete-recipe" data-id="${recipe.id}" style="color: var(--danger-color);">🗑️ O'chirish</button>
                </div>
            </div>
        `;
    }
    
    openModal(recipe = null) {
        this.editingId = recipe?.id || null;
        document.getElementById('modalTitle').textContent = recipe ? 'Retseptni tahrirlash' : 'Yangi retsept';
        document.getElementById('recipeForm').reset();
        document.getElementById('ingredientsList').innerHTML = '';
        
        this.populateProductSelect();
        
        if (recipe) {
            document.getElementById('recipeId').value = recipe.id;
            document.getElementById('productSelect').value = recipe.product_id;
            document.getElementById('recipeName').value = recipe.name;
            document.getElementById('recipeDescription').value = recipe.description || '';
            document.getElementById('preparationTime').value = recipe.preparation_time || 30;
            
            // Ingredientlarni yuklash
            if (recipe.items) {
                recipe.items.forEach(item => this.addIngredientRow(item));
            }
        }
        
        this.modal.open();
    }
    
    addIngredientRow(data = null) {
        const container = document.getElementById('ingredientsList');
        const row = document.createElement('div');
        row.className = 'ingredient-row';
        
        const ingredientsOptions = this.ingredients.map(i => 
            `<option value="${i.product_id}" ${data?.ingredient_id === i.product_id ? 'selected' : ''}>${i.product?.name}</option>`
        ).join('');
        
        row.innerHTML = `
            <select class="ingredient-select" required>
                <option value="">Tanlang</option>
                ${ingredientsOptions}
            </select>
            <input type="number" class="ingredient-quantity" placeholder="Miqdor" step="0.01" min="0.01" value="${data?.quantity || ''}" required>
            <input type="text" class="ingredient-unit" placeholder="O'lchov" value="${data?.unit || 'kg'}">
            <button type="button" class="remove-ingredient" onclick="this.closest('.ingredient-row').remove()">✕</button>
        `;
        
        container.appendChild(row);
    }
    
    async saveRecipe() {
        const recipeId = document.getElementById('recipeId').value;
        const productId = document.getElementById('productSelect').value;
        const name = document.getElementById('recipeName').value;
        const description = document.getElementById('recipeDescription').value;
        const preparationTime = parseInt(document.getElementById('preparationTime').value);
        
        if (!productId || !name) {
            showToast('Mahsulot va retsept nomi majburiy', 'warning');
            return;
        }
        
        // Ingredientlarni yig'ish
        const items = [];
        document.querySelectorAll('.ingredient-row').forEach(row => {
            const select = row.querySelector('.ingredient-select');
            const quantity = row.querySelector('.ingredient-quantity');
            const unit = row.querySelector('.ingredient-unit');
            
            if (select.value && quantity.value) {
                items.push({
                    ingredient_id: parseInt(select.value),
                    quantity: parseFloat(quantity.value),
                    unit: unit.value || 'kg'
                });
            }
        });
        
        if (items.length === 0) {
            showToast('Kamida bitta ingredient qo\'shing', 'warning');
            return;
        }
        
        try {
            const data = {
                product_id: parseInt(productId),
                name: name,
                description: description,
                preparation_time: preparationTime,
                items: items
            };
            
            if (recipeId) {
                await this.api.put(`/recipes/${recipeId}`, data);
                showToast('Retsept yangilandi', 'success');
            } else {
                await this.api.post('/recipes', data);
                showToast('Retsept yaratildi', 'success');
            }
            
            await this.loadData();
            this.renderRecipes();
            this.modal.close();
        } catch (error) {
            console.error('Saqlashda xatolik:', error);
            showToast('Saqlashda xatolik', 'error');
        }
    }
    
    editRecipe(id) {
        const recipe = this.recipes.find(r => r.id == id);
        if (recipe) {
            this.openModal(recipe);
        }
    }
    
    async deleteRecipe(id) {
        if (!confirm('Retseptni o\'chirishni xohlaysizmi?')) return;
        
        try {
            await this.api.delete(`/recipes/${id}`);
            showToast('Retsept o\'chirildi', 'success');
            await this.loadData();
            this.renderRecipes();
        } catch (error) {
            console.error('O\'chirishda xatolik:', error);
            showToast('O\'chirishda xatolik', 'error');
        }
    }
    
    filterRecipes() {
        const searchTerm = document.getElementById('searchInput').value.toLowerCase();
        const category = document.getElementById('categoryFilter').value;
        
        let filtered = this.recipes;
        
        if (searchTerm) {
            filtered = filtered.filter(r => 
                r.name.toLowerCase().includes(searchTerm) ||
                (r.description && r.description.toLowerCase().includes(searchTerm))
            );
        }
        
        if (category) {
            filtered = filtered.filter(r => {
                const product = this.products.find(p => p.id === r.product_id);
                return product?.category?.name === category;
            });
        }
        
        const grid = document.getElementById('recipesGrid');
        if (filtered.length === 0) {
            grid.innerHTML = `
                <div class="empty-state" style="grid-column: 1/-1; text-align: center; padding: 60px;">
                    <h3>🔍 Retsept topilmadi</h3>
                    <p>Boshqa kalit so'z yoki filtr bilan qidirib ko'ring</p>
                </div>
            `;
        } else {
            grid.innerHTML = filtered.map(recipe => this.createRecipeCard(recipe)).join('');
            
            grid.querySelectorAll('.edit-recipe').forEach(btn => {
                btn.addEventListener('click', () => this.editRecipe(btn.dataset.id));
            });
            
            grid.querySelectorAll('.delete-recipe').forEach(btn => {
                btn.addEventListener('click', () => this.deleteRecipe(btn.dataset.id));
            });
        }
    }
}

// Sahifa yuklanganda ishga tushirish
document.addEventListener('DOMContentLoaded', () => {
    new RecipesModule();
});

export default RecipesModule;