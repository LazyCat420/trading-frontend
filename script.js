document.addEventListener('DOMContentLoaded', function() {
    function fetchData(url, elementId, dataKey, displayType = 'list') {
        fetch(url)
            .then(response => response.json())
            .then(data => {
                const element = document.getElementById(elementId);
                if (!element) return;

                if (displayType === 'list') {
                    element.innerHTML = '';
                    
                    if (url.includes('watchlist')) {
                        // Handle sector watchlists
                        const sectorWatchlists = data.watchlist[0].sector_watchlists;
                        const prices = data.watchlist[0].prices || {};
                        
                        const sortedSectors = Object.entries(sectorWatchlists).sort(([a], [b]) => a.localeCompare(b));
                        
                        sortedSectors.forEach(([sector, stocks]) => {
                            const sectorDiv = document.createElement('div');
                            sectorDiv.className = 'sector-group';
                            sectorDiv.innerHTML = `
                                <h3 class="sector-title">${sector}</h3>
                                <div class="sector-stocks">
                                    ${stocks.map(symbol => {
                                        const stockPrice = prices[symbol] || {};
                                        const price = stockPrice.price || stockPrice.previousClose || 0;
                                        const displayPrice = price.toFixed(2);
                                        const change = stockPrice.changePercent || 0;
                                        const displayChange = change.toFixed(2);
                                        const isPositive = change >= 0;
                                        const isMarketClosed = stockPrice.isMarketClosed;
                                        
                                        return `
                                            <div class="stock-item">
                                                <span class="symbol">${symbol}</span>
                                                <div class="price flip-board">
                                                    ${displayPrice.split('').map(digit => 
                                                        `<span class="digit">${digit}</span>`
                                                    ).join('')}
                                                </div>
                                                <div class="change flip-board ${isPositive ? 'positive' : 'negative'}">
                                                    ${(isPositive ? '+' : '') + displayChange + '%'}
                                                </div>
                                                ${isMarketClosed ? '<span class="market-status">Market Closed</span>' : ''}
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            `;
                            element.appendChild(sectorDiv);
                        });
                    } else if (url.includes('trades')) {
                        // Handle trades display (compact version)
                        const trades = data.trades;
                        trades.slice(0, 10).forEach(trade => { // Show only last 10 trades
                            const tradeItem = document.createElement('div');
                            tradeItem.className = 'trade-item';
                            tradeItem.innerHTML = `
                                <div class="trade-header">
                                    <span class="trade-symbol">${trade.ticker}</span>
                                    <span class="trade-action ${trade.action}">${trade.action}</span>
                                </div>
                                <div class="trade-details">
                                    <span>${trade.shares} @ $${trade.price.toFixed(2)}</span>
                                    <span class="trade-amount">$${trade.amount.toFixed(2)}</span>
                                </div>
                            `;
                            element.appendChild(tradeItem);
                        });
                    }
                } else if (displayType === 'flip-board') {
                    if (url.includes('summary')) {
                        const summary = data.summary;
                        const portfolioDetails = summary.portfolio_details || {};
                        
                        const portfolioDiv = document.createElement('div');
                        portfolioDiv.className = 'portfolio-summary';
                        
                        portfolioDiv.innerHTML = `
                            <div class="summary-header">
                                <div class="summary-total">
                                    <h3>Portfolio Value</h3>
                                    <div class="flip-board value">
                                        $${summary.total_portfolio_value.toFixed(2)}
                                    </div>
                                </div>
                                <div class="summary-pl">
                                    <h3>Total P/L</h3>
                                    <div class="flip-board ${summary.total_unrealized_pl >= 0 ? 'positive' : 'negative'}">
                                        ${summary.total_unrealized_pl >= 0 ? '+' : ''}$${summary.total_unrealized_pl.toFixed(2)}
                                        (${summary.total_pl_percentage.toFixed(2)}%)
                                    </div>
                                </div>
                            </div>
                            <div class="holdings-table">
                                <table>
                                    <thead>
                                        <tr>
                                            <th>Symbol</th>
                                            <th>Shares</th>
                                            <th>Buy Price</th>
                                            <th>Current</th>
                                            <th>Total Value</th>
                                            <th>P/L</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${Object.entries(portfolioDetails).map(([symbol, details]) => `
                                            <tr>
                                                <td class="symbol">${symbol}</td>
                                                <td class="shares">${details.shares}</td>
                                                <td class="price">$${details.purchase_price.toFixed(2)}</td>
                                                <td class="price">$${details.current_price.toFixed(2)}</td>
                                                <td class="value">$${details.current_value.toFixed(2)}</td>
                                                <td class="pl ${details.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                                                    ${details.unrealized_pl >= 0 ? '+' : ''}$${details.unrealized_pl.toFixed(2)}
                                                    <span class="pl-percent">
                                                        (${details.pl_percentage.toFixed(2)}%)
                                                    </span>
                                                </td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        `;
                        element.innerHTML = '';
                        element.appendChild(portfolioDiv);
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                const element = document.getElementById(elementId);
                if (element) element.textContent = "Error loading data.";
            });
    }

    function updateFlipBoard(elementId, value, isPositive = true) {
        const element = document.getElementById(elementId);
        if (!element) {
            console.error(`Flip board element not found: ${elementId}`);
            return;
        }

        element.innerHTML = ''; // Clear existing digits
        const digits = value.toString().split('');
        
        if (isPositive !== undefined) {
            element.classList.remove('positive', 'negative');
            element.classList.add(isPositive ? 'positive' : 'negative');
        }

        digits.forEach(digit => {
            const digitSpan = document.createElement('span');
            digitSpan.className = 'digit';
            digitSpan.textContent = digit;
            element.appendChild(digitSpan);
        });
    }

    // Initial data fetch
    fetchData('http://localhost:5000/watchlist', 'watchlist-display', 'watchlist', 'list');
    fetchData('http://localhost:5000/trades', 'trades-display', 'trades', 'list');
    fetchData('http://localhost:5000/summary', 'summary-display', 'summary', 'flip-board');

    // Refresh data every 30 seconds
    setInterval(() => {
        fetchData('http://localhost:5000/watchlist', 'watchlist-display', 'watchlist', 'list');
        fetchData('http://localhost:5000/trades', 'trades-display', 'trades', 'list');
        fetchData('http://localhost:5000/summary', 'summary-display', 'summary', 'flip-board');
    }, 30000);
}); 