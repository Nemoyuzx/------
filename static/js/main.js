// 全局变量
let hourlyChartData, dailyChartData, monthlyChartData;
let currentChart = 'daily'; // 当前显示的图表类型

// 初始化图表数据（在HTML中设置）
function initChartData(hourly, daily, monthly) {
    try {
        hourlyChartData = hourly || [];
        dailyChartData = daily || [];
        monthlyChartData = monthly || [];
    } catch (e) {
        console.error('图表数据解析错误:', e);
        hourlyChartData = [];
        dailyChartData = [];
        monthlyChartData = [];
    }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 从数据属性中获取图表数据
    const chartDataEl = document.getElementById('chartData');
    if (chartDataEl) {
        try {
            const hourlyData = JSON.parse(chartDataEl.dataset.hourly || '[]');
            const dailyData = JSON.parse(chartDataEl.dataset.daily || '[]');
            const monthlyData = JSON.parse(chartDataEl.dataset.monthly || '[]');
            
            hourlyChartData = hourlyData;
            dailyChartData = dailyData;
            monthlyChartData = monthlyData;
        } catch (e) {
            console.error('图表数据解析错误:', e);
            hourlyChartData = [];
            dailyChartData = [];
            monthlyChartData = [];
        }
    }

    // 初始化图表和设置
    drawCharts();
    loadSettings();
});

// 显示提示信息
function showAlert(message, type = 'success') {
    const alertEl = document.createElement('div');
    alertEl.className = `alert alert-${type}`;
    alertEl.innerHTML = message;
    
    const container = document.querySelector('.container');
    container.insertBefore(alertEl, container.children[1]);
    
    setTimeout(() => {
        alertEl.remove();
    }, 5000);
}

// 设置按钮加载状态
function setButtonLoading(button, loading) {
    if (loading) {
        button.disabled = true;
        button.classList.add('loading');
    } else {
        button.disabled = false;
        button.classList.remove('loading');
    }
}

// 立即检查
function checkNow(event) {
    const btn = event.target.closest('.btn');
    setButtonLoading(btn, true);
    
    fetch('/api/check', { method: 'POST' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('检查完成！', 'success');
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showAlert(data.message || '检查失败', 'error');
            }
        })
        .catch(error => {
            console.error('检查失败:', error);
            showAlert('检查失败，请稍后重试', 'error');
        })
        .finally(() => {
            setButtonLoading(btn, false);
        });
}

// 刷新数据
function refreshData(event) {
    const btn = event.target.closest('.btn');
    setButtonLoading(btn, true);
    
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            // 更新统计信息
            if (data.latest && data.latest.length >= 3 && data.latest[2] !== null) {
                document.getElementById('current-balance').textContent = data.latest[2].toFixed(2);
            }
            if (data.today_usage !== undefined && data.today_usage !== null) {
                document.getElementById('today-usage').textContent = data.today_usage.toFixed(2);
            }
            if (data.month_usage !== undefined && data.month_usage !== null) {
                document.getElementById('month-usage').textContent = data.month_usage.toFixed(2);
            }
            if (data.latest && data.latest.length >= 2) {
                document.getElementById('last-update').textContent = data.latest[1] || '--';
            }
            
            // 更新图表数据
            if (data.balance_trend_hourly) {
                hourlyChartData = data.balance_trend_hourly;
            }
            if (data.balance_trend_daily) {
                dailyChartData = data.balance_trend_daily;
            }
            if (data.balance_trend_monthly) {
                monthlyChartData = data.balance_trend_monthly;
            }
            drawCharts();
            
            showAlert('数据刷新成功！', 'success');
        })
        .catch(error => {
            console.error('刷新失败:', error);
            showAlert('刷新失败，请稍后重试', 'error');
        })
        .finally(() => {
            setButtonLoading(btn, false);
        });
}

// 清空所有记录
function clearAllRecords(event) {
    if (!confirm('确定要清空所有历史记录吗？此操作不可恢复。')) {
        return;
    }
    
    const btn = event.target.closest('.btn');
    setButtonLoading(btn, true);
    
    fetch('/api/records', { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('记录清空成功！', 'success');
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showAlert(data.message || '清空失败', 'error');
            }
        })
        .catch(error => {
            console.error('清空失败:', error);
            showAlert('清空失败，请稍后重试', 'error');
        })
        .finally(() => {
            setButtonLoading(btn, false);
        });
}

// 删除单条记录
function deleteRecord(recordId, event) {
    if (!confirm('确定要删除这条记录吗？')) {
        return;
    }
    
    fetch(`/api/records/${recordId}`, { method: 'DELETE' })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('记录删除成功！', 'success');
                // 移除表格行
                event.target.closest('tr').remove();
            } else {
                showAlert(data.message || '删除失败', 'error');
            }
        })
        .catch(error => {
            console.error('删除失败:', error);
            showAlert('删除失败，请稍后重试', 'error');
        });
}

// 打开设置模态框
function openSettings() {
    document.getElementById('settingsModal').style.display = 'block';
    loadSettings();
}

// 关闭设置模态框
function closeSettings() {
    document.getElementById('settingsModal').style.display = 'none';
}

// 加载设置
function loadSettings() {
    fetch('/api/config')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                document.getElementById('threshold').value = data.config.threshold || 10.00;
                document.getElementById('emails').value = (data.config.emails || []).join('\n');
                document.getElementById('checkFrequency').value = data.config.check_frequency || 30;
            }
        })
        .catch(error => {
            console.error('加载设置失败:', error);
        });
}

// 图表切换函数
function switchChart(chartType) {
    // 更新标签状态
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`[data-chart="${chartType}"]`).classList.add('active');
    
    // 切换图表容器显示
    document.getElementById('hourlyChartContainer').style.display = chartType === 'hourly' ? 'block' : 'none';
    document.getElementById('dailyChartContainer').style.display = chartType === 'daily' ? 'block' : 'none';
    document.getElementById('monthlyChartContainer').style.display = chartType === 'monthly' ? 'block' : 'none';
    
    currentChart = chartType;
    drawCharts();
}

// 绘制所有图表
function drawCharts() {
    if (currentChart === 'hourly') {
        drawChart('hourlyChart', hourlyChartData, '按小时余额趋势 (元)', 'hourly');
    } else if (currentChart === 'daily') {
        drawChart('dailyChart', dailyChartData, '按天余额趋势 (元)', 'daily');
    } else {
        drawChart('monthlyChart', monthlyChartData, '按月余额趋势 (元)', 'monthly');
    }
}

// 绘制余额趋势图
function drawChart(canvasId, chartData, title, chartType) {
    if (!chartData || chartData.length === 0) {
        return;
    }
    
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    
    // 设置Canvas尺寸
    canvas.width = canvas.offsetWidth * 2;
    canvas.height = canvas.offsetHeight * 2;
    ctx.scale(2, 2);
    
    const width = canvas.offsetWidth;
    const height = canvas.offsetHeight;
    const margin = 60;
    const chartWidth = width - 2 * margin;
    const chartHeight = height - 2 * margin;
    
    // 清空画布
    ctx.clearRect(0, 0, width, height);
    
    // 数据处理
    const balances = chartData.map(item => item[1]);
    const maxBalance = Math.max(...balances);
    const minBalance = Math.min(...balances);
    const balanceRange = maxBalance - minBalance || 1;
    
    // 绘制背景
    ctx.fillStyle = '#f8f9fa';
    ctx.fillRect(margin, margin, chartWidth, chartHeight);
    
    // 绘制网格线
    ctx.strokeStyle = '#e1e5e9';
    ctx.lineWidth = 1;
    
    // 水平网格线
    for (let i = 0; i <= 5; i++) {
        const y = margin + (chartHeight / 5) * i;
        ctx.beginPath();
        ctx.moveTo(margin, y);
        ctx.lineTo(margin + chartWidth, y);
        ctx.stroke();
        
        // Y轴标签
        const value = maxBalance - (balanceRange / 5) * i;
        ctx.fillStyle = '#666';
        ctx.font = '12px Arial';
        ctx.textAlign = 'right';
        ctx.fillText((value !== null && value !== undefined) ? value.toFixed(2) : "--", margin - 10, y + 4);
    }
    
    // 垂直网格线
    const stepX = chartWidth / Math.max(chartData.length - 1, 1);
    for (let i = 0; i < chartData.length; i++) {
        const x = margin + stepX * i;
        ctx.beginPath();
        ctx.moveTo(x, margin);
        ctx.lineTo(x, margin + chartHeight);
        ctx.stroke();
    }
    
    // 绘制折线
    if (chartData.length > 1) {
        ctx.strokeStyle = '#667eea';
        ctx.lineWidth = 3;
        ctx.beginPath();
        
        for (let i = 0; i < chartData.length; i++) {
            const x = margin + stepX * i;
            const balance = chartData[i][1];
            const y = margin + (maxBalance - balance) / balanceRange * chartHeight;
            
            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        }
        ctx.stroke();
        
        // 绘制数据点
        ctx.fillStyle = '#667eea';
        for (let i = 0; i < chartData.length; i++) {
            const x = margin + stepX * i;
            const balance = chartData[i][1];
            const y = margin + (maxBalance - balance) / balanceRange * chartHeight;
            
            ctx.beginPath();
            ctx.arc(x, y, 4, 0, 2 * Math.PI);
            ctx.fill();
            
            // 数据点标签
            ctx.fillStyle = '#333';
            ctx.font = '11px Arial';
            ctx.textAlign = 'center';
            ctx.fillText((balance !== null && balance !== undefined) ? balance.toFixed(2) : "--", x, y - 10);
            ctx.fillStyle = '#667eea';
        }
    }
    
    // 绘制X轴标签
    ctx.fillStyle = '#666';
    ctx.font = '11px Arial';
    ctx.textAlign = 'center';
    for (let i = 0; i < chartData.length; i++) {
        const x = margin + stepX * i;
        let label;
        if (chartType === 'hourly') {
            // 按小时显示：显示小时格式
            const date = new Date(chartData[i][0]);
            label = date.getHours() + ':00';
        } else if (chartType === 'monthly') {
            // 按月显示：显示年-月格式
            label = chartData[i][0];
        } else {
            // 按天显示：显示月/日格式
            const date = new Date(chartData[i][0]);
            label = (date.getMonth() + 1) + '/' + date.getDate();
        }
        ctx.fillText(label, x, margin + chartHeight + 20);
    }
    
    // 绘制坐标轴
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(margin, margin);
    ctx.lineTo(margin, margin + chartHeight);
    ctx.lineTo(margin + chartWidth, margin + chartHeight);
    ctx.stroke();
    
    // 添加标题
    ctx.fillStyle = '#333';
    ctx.font = 'bold 16px Arial';
    ctx.textAlign = 'center';
    ctx.fillText(title, width / 2, 30);
}

// 自动刷新数据（每10分钟）
setInterval(() => {
    fetch('/api/stats')
        .then(response => response.json())
        .then(data => {
            if (data.latest && data.latest[2] !== null && data.latest[2] !== undefined) {
                document.getElementById('current-balance').textContent = data.latest[2].toFixed(2);
            }
            if (data.today_usage !== undefined && data.today_usage !== null) {
                document.getElementById('today-usage').textContent = data.today_usage.toFixed(2);
            }
            if (data.month_usage !== undefined && data.month_usage !== null) {
                document.getElementById('month-usage').textContent = data.month_usage.toFixed(2);
            }
            if (data.latest && data.latest[1]) {
                document.getElementById('last-update').textContent = data.latest[1] || '--';
            }
            if (data.balance_trend_hourly) {
                hourlyChartData = data.balance_trend_hourly;
            }
            if (data.balance_trend_daily) {
                dailyChartData = data.balance_trend_daily;
            }
            if (data.balance_trend_monthly) {
                monthlyChartData = data.balance_trend_monthly;
            }
            drawCharts();
        })
        .catch(error => console.error('自动刷新失败:', error));
}, 600000); // 10分钟

// 点击模态框外部关闭
window.addEventListener('click', function(event) {
    const modal = document.getElementById('settingsModal');
    if (event.target === modal) {
        closeSettings();
    }
});

// 日志相关函数

// 切换日志显示
function toggleLogs(event) {
    const logsCard = document.getElementById('logsCard');
    const btn = event.target.closest('.btn');
    const btnText = btn.querySelector('.btn-text');
    
    if (logsCard.style.display === 'none') {
        logsCard.style.display = 'block';
        btnText.textContent = '隐藏日志';
        refreshLogs(null);
        
        // 滚动到日志模块
        logsCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
        logsCard.style.display = 'none';
        btnText.textContent = '查看日志';
    }
}

// 刷新日志
async function refreshLogs(event) {
    const btn = event?.target?.closest('.btn');
    if (btn) setButtonLoading(btn, true);
    
    try {
        const limit = document.getElementById('logLimit')?.value || 50;
        const level = document.getElementById('logLevel')?.value || 'all';
        
        const response = await fetch(`/api/logs?limit=${limit}&level=${level}`);
        const data = await response.json();
        
        if (data.success) {
            displayLogs(data.logs);
        } else {
            document.getElementById('log-content').innerHTML = 
                '<div class="log-empty">加载日志失败: ' + (data.message || '未知错误') + '</div>';
        }
    } catch (error) {
        console.error('获取日志失败:', error);
        document.getElementById('log-content').innerHTML = 
            '<div class="log-empty">网络错误，无法获取日志</div>';
    } finally {
        if (btn) setButtonLoading(btn, false);
    }
}

// 显示日志
function displayLogs(logs) {
    const logContent = document.getElementById('log-content');
    
    if (!logs || logs.length === 0) {
        logContent.innerHTML = '<div class="log-empty">暂无日志记录</div>';
        return;
    }
    
    const logHtml = logs.map(log => {
        const timestamp = log.timestamp || '';
        const level = log.level || 'INFO';
        const message = log.message || '';
        
        return `
            <div class="log-entry ${level}">
                <span class="log-timestamp">${timestamp}</span>
                <span class="log-level ${level}">[${level}]</span>
                <span class="log-message">${escapeHtml(message)}</span>
            </div>
        `;
    }).join('');
    
    logContent.innerHTML = logHtml;
    
    // 滚动到底部显示最新日志
    logContent.scrollTop = logContent.scrollHeight;
}

// 过滤日志
function filterLogs() {
    refreshLogs(null);
}

// 清空日志
async function clearLogs(event) {
    if (!confirm('确定要清空所有日志吗？此操作不可恢复！')) {
        return;
    }
    
    const btn = event?.target?.closest('.btn');
    if (btn) setButtonLoading(btn, true);
    
    try {
        const response = await fetch('/api/logs', {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            showAlert('日志已清空', 'success');
            document.getElementById('log-content').innerHTML = 
                '<div class="log-empty">暂无日志记录</div>';
        } else {
            showAlert('清空日志失败: ' + (data.message || '未知错误'), 'error');
        }
    } catch (error) {
        console.error('清空日志失败:', error);
        showAlert('网络错误，清空日志失败', 'error');
    } finally {
        if (btn) setButtonLoading(btn, false);
    }
}

// HTML转义函数
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, function(m) { return map[m]; });
}

// 设置表单提交处理
document.addEventListener('DOMContentLoaded', function() {
    const settingsForm = document.getElementById('settingsForm');
    if (settingsForm) {
        settingsForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const btn = this.querySelector('button[type="submit"]');
            setButtonLoading(btn, true);
            
            const formData = {
                threshold: parseFloat(document.getElementById('threshold').value),
                emails: document.getElementById('emails').value.split('\n').filter(email => email.trim()),
                check_frequency: parseInt(document.getElementById('checkFrequency').value)
            };
            
            fetch('/api/config', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(formData)
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showAlert('设置保存成功！', 'success');
                    closeSettings();
                } else {
                    showAlert(data.message || '保存失败', 'error');
                }
            })
            .catch(error => {
                console.error('保存设置失败:', error);
                showAlert('保存失败，请稍后重试', 'error');
            })
            .finally(() => {
                setButtonLoading(btn, false);
            });
        });
    }
});
