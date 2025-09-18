// Hotel Recommender Frontend Application
class HotelRecommenderApp {
    constructor() {
        this.baseURL = '';  // Same origin
        this.form = document.getElementById('hotel-search-form');
        this.resultsSection = document.getElementById('results-section');
        this.resultsContainer = document.getElementById('results-container');
        this.errorSection = document.getElementById('error-section');
        this.errorMessage = document.getElementById('error-message');
        this.searchBtn = document.getElementById('search-btn');
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.setDefaultDate();
    }
    
    bindEvents() {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
        
        // Date and weekday mutual exclusion
        const dateInput = document.getElementById('date');
        const weekdaySelect = document.getElementById('weekday');
        
        dateInput.addEventListener('change', () => {
            if (dateInput.value) {
                weekdaySelect.value = '';
                weekdaySelect.disabled = true;
            } else {
                weekdaySelect.disabled = false;
            }
        });
        
        weekdaySelect.addEventListener('change', () => {
            if (weekdaySelect.value) {
                dateInput.value = '';
                dateInput.disabled = true;
            } else {
                dateInput.disabled = false;
            }
        });
    }
    
    setDefaultDate() {
        const today = new Date();
        const tomorrow = new Date(today);
        tomorrow.setDate(tomorrow.getDate() + 1);
        
        const dateStr = tomorrow.toISOString().split('T')[0];
        document.getElementById('date').value = dateStr;
    }
    
    async handleSubmit(e) {
        e.preventDefault();
        
        const formData = new FormData(this.form);
        const requestData = {
            stations: [formData.get('station_name').trim()],
            price_max: parseInt(formData.get('price_limit'))
        };
        
        // Add date or weekday if provided
        const date = formData.get('date');
        const weekday = formData.get('weekday');
        
        if (date) {
            requestData.date = date;
        } else if (weekday) {
            requestData.weekday = weekday;
        }
        
        await this.searchHotels(requestData);
    }
    
    async searchHotels(requestData) {
        this.setLoadingState(true);
        this.hideResults();
        this.hideError();
        
        try {
            const response = await fetch('/api/suggest', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(requestData)
            });
            
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
            }
            
            const data = await response.json();
            this.displayResults(data);
            
        } catch (error) {
            console.error('Search error:', error);
            this.displayError(error.message);
        } finally {
            this.setLoadingState(false);
        }
    }
    
    setLoadingState(loading) {
        const btnText = this.searchBtn.querySelector('.btn-text');
        const spinner = this.searchBtn.querySelector('.spinner');
        
        if (loading) {
            this.searchBtn.disabled = true;
            btnText.style.display = 'none';
            spinner.style.display = 'inline';
        } else {
            this.searchBtn.disabled = false;
            btnText.style.display = 'inline';
            spinner.style.display = 'none';
        }
    }
    
    displayResults(data) {
        if (!data.results || data.results.length === 0) {
            this.displayNoResults();
            return;
        }

        const html = data.results.map(hotel => this.renderHotelCard(hotel)).join('');
        this.resultsContainer.innerHTML = html;
        this.showResults();
    }
    
    displayNoResults() {
        this.resultsContainer.innerHTML = `
            <div class="no-results">
                <div class="no-results-icon">🏨</div>
                <h3>検索結果が見つかりませんでした</h3>
                <p>条件を変更して再度お試しください。</p>
            </div>
        `;
        this.showResults();
    }
    
    renderHotelCard(hotel) {
        const price = hotel.price_total ? `¥${hotel.price_total.toLocaleString()}～` : '料金要確認';
        const distance = hotel.distance_text ? `📍 ${hotel.distance_text}` : '';
        
        return `
            <div class="hotel-card">
                <div class="hotel-header">
                    <div class="hotel-info">
                        <div class="hotel-name">${this.escapeHtml(hotel.name)}</div>
                        <div class="hotel-price">${price}</div>
                    </div>
                </div>
                
                <div class="hotel-details">
                    ${distance ? `<div class="detail-item"><span class="detail-icon">📍</span>距離: ${distance}</div>` : ''}
                    ${hotel.reason ? `<div class="detail-item"><span class="detail-icon">�</span>推薦理由: ${this.escapeHtml(hotel.reason)}</div>` : ''}
                    ${hotel.cancellable !== null ? `<div class="detail-item"><span class="detail-icon">${hotel.cancellable ? '✅' : '❌'}</span>キャンセル: ${hotel.cancellable ? '可能' : '不可'}</div>` : ''}
                    ${hotel.highlights && hotel.highlights.length > 0 ? `<div class="detail-item"><span class="detail-icon">✨</span>特徴: ${hotel.highlights.slice(0, 3).map(h => this.escapeHtml(h)).join(', ')}</div>` : ''}
                </div>
                
                <div class="hotel-actions">
                    ${hotel.booking_url ? `
                        <a href="${this.escapeHtml(hotel.booking_url)}" 
                           target="_blank" 
                           rel="noopener noreferrer" 
                           class="btn btn-primary">
                            🔗 楽天トラベルで予約
                        </a>
                    ` : ''}
                </div>
            </div>
        `;
    }
    
    displayError(message) {
        this.errorMessage.innerHTML = `
            <div class="error-message">
                ${this.escapeHtml(message)}
            </div>
        `;
        this.showError();
    }
    
    showResults() {
        this.resultsSection.style.display = 'block';
        this.resultsSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    hideResults() {
        this.resultsSection.style.display = 'none';
    }
    
    showError() {
        this.errorSection.style.display = 'block';
        this.errorSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    hideError() {
        this.errorSection.style.display = 'none';
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Initialize the app when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    new HotelRecommenderApp();
});

// Add some utility functions for better UX
document.addEventListener('DOMContentLoaded', () => {
    // Add input validation feedback
    const inputs = document.querySelectorAll('input[required], select[required]');
    inputs.forEach(input => {
        input.addEventListener('invalid', (e) => {
            e.target.classList.add('invalid');
        });
        
        input.addEventListener('input', (e) => {
            if (e.target.validity.valid) {
                e.target.classList.remove('invalid');
            }
        });
    });
    
    // Add price range slider functionality
    const priceInput = document.getElementById('price-limit');
    priceInput.addEventListener('input', (e) => {
        const value = parseInt(e.target.value);
        const hint = e.target.nextElementSibling;
        hint.textContent = `1泊あたりの上限金額: ¥${value.toLocaleString()}`;
    });
});

// Add CSS for validation states
const style = document.createElement('style');
style.textContent = `
    .invalid {
        border-color: #dc3545 !important;
        box-shadow: 0 0 0 3px rgba(220, 53, 69, 0.1) !important;
    }
    
    .invalid:focus {
        border-color: #dc3545 !important;
        box-shadow: 0 0 0 3px rgba(220, 53, 69, 0.25) !important;
    }
`;
document.head.appendChild(style);