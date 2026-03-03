import { useState, useEffect } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, AreaChart, Area, Line } from 'recharts';
import { Play, TrendingUp, Activity, BarChart3, Settings, History, ChevronRight, Loader2 } from 'lucide-react';
import { toast } from 'sonner';

interface StrategyInfo {
  key: string;
  name: string;
  ticker: string;
  tickers_needed: string[];
}

interface BacktestHistoryItem {
  id: string;
  strategy: string;
  strategy_name: string;
  years: number;
  initial_cash: number;
  data_start: string;
  data_end: string;
  trading_days: number;
  total_return: number;
  cagr: number;
  max_drawdown: number;
  sharpe_ratio: number;
  created_at: string;
}

interface Metrics {
  total_return: number;
  cagr: number;
  max_drawdown: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  win_rate?: number;
  total_trades?: number;
  benchmark_total_return?: number;
  benchmark_max_drawdown?: number;
}

interface EquityPoint {
  date: string;
  value: number;
}

interface Trade {
  date: string;
  ticker: string;
  action: string;
  quantity: number;
  price: number;
  pnl: number;
  details: string;
}

interface FullBacktestResult {
  id: string;
  strategy: string;
  strategy_name: string;
  years: number;
  initial_cash: number;
  data_start: string;
  data_end: string;
  trading_days: number;
  metrics: Metrics;
  equity_curve: EquityPoint[];
  benchmark_equity_curve: EquityPoint[];
  trades: Trade[];
}

const API_BASE = 'http://localhost:8000';

function App() {
  const [activeTab, setActiveTab] = useState('backtest');
  const [loading, setLoading] = useState(false);
  
  const [strategies, setStrategies] = useState<StrategyInfo[]>([]);
  const [backtests, setBacktests] = useState<BacktestHistoryItem[]>([]);
  const [selectedResult, setSelectedResult] = useState<FullBacktestResult | null>(null);

  // Form state
  const [selectedStrategy, setSelectedStrategy] = useState('hydra_v6');
  const [years, setYears] = useState(5);
  const [initialCash, setInitialCash] = useState(100000);

  useEffect(() => {
    fetchStrategies();
    fetchBacktests();
  }, []);

  const fetchStrategies = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/strategies`);
      if (response.ok) {
        const data = await response.json();
        setStrategies(data.strategies);
      }
    } catch (error) {
      console.error('Error fetching strategies:', error);
    }
  };

  const fetchBacktests = async () => {
    try {
      const response = await fetch(`${API_BASE}/api/backtests?limit=20`);
      if (response.ok) {
        const data = await response.json();
        setBacktests(data.history);
      }
    } catch (error) {
      console.error('Error fetching backtests:', error);
    }
  };

  const runBacktest = async () => {
    setLoading(true);
    try {
      const payload = {
        strategy: selectedStrategy,
        years: years,
        initial_cash: initialCash,
        force_refresh: false
      };

      const response = await fetch(`${API_BASE}/api/backtest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (response.ok) {
        const result = await response.json();
        toast.success('Backtest completed successfully!');
        setSelectedResult(result);
        fetchBacktests(); // Refresh history
        setActiveTab('results');
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Backtest failed');
      }
    } catch (error) {
      toast.error('Failed to run backtest. Is the backend running?');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const loadBacktestDetails = async (id: string) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/backtest/${id}`);
      if (response.ok) {
        const result = await response.json();
        setSelectedResult(result);
        setActiveTab('results');
      } else {
        toast.error('Failed to load backtest details');
      }
    } catch (error) {
      console.error('Error fetching backtest details:', error);
    } finally {
      setLoading(false);
    }
  };

  const formatPercent = (val: number | undefined) => {
    if (val === undefined) return '-';
    return `${(val * 100).toFixed(2)}%`;
  };
  const formatCurrency = (val: number | undefined) => {
    if (val === undefined) return '-';
    return `$${val.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };

  // Combine equity and benchmark for chart
  const getChartData = () => {
    if (!selectedResult) return [];
    return selectedResult.equity_curve.map((eq, i) => {
      const bench = selectedResult.benchmark_equity_curve[i];
      return {
        date: eq.date,
        Portfolio: eq.value,
        Benchmark: bench ? bench.value : null
      };
    });
  };

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <header className="bg-white border-b border-slate-200 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <div className="bg-blue-600 p-2 rounded-lg">
                <TrendingUp className="h-6 w-6 text-white" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900">Unified Backtest Lab</h1>
                <p className="text-xs text-slate-500">AlphaPilot Quantitative Trading Engine</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Badge variant="secondary" className="gap-1">
                <div className="w-2 h-2 rounded-full bg-green-500" />
                API Connected
              </Badge>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="space-y-6">
          <TabsList className="grid w-full grid-cols-3 lg:w-[400px]">
            <TabsTrigger value="backtest" className="gap-2">
              <Play className="h-4 w-4" />
              Run Backtest
            </TabsTrigger>
            <TabsTrigger value="results" className="gap-2">
              <BarChart3 className="h-4 w-4" />
              Results
            </TabsTrigger>
            <TabsTrigger value="history" className="gap-2">
              <History className="h-4 w-4" />
              DB History
            </TabsTrigger>
          </TabsList>

          {/* Backtest Tab */}
          <TabsContent value="backtest" className="space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Strategy Selection */}
              <Card>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <Settings className="h-5 w-5" />
                    Strategy Configuration
                  </CardTitle>
                  <CardDescription>Select strategy and timeframe to run a simulation against local database.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  <div className="space-y-2">
                    <Label>Strategy</Label>
                    <Select value={selectedStrategy} onValueChange={setSelectedStrategy}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select a strategy..." />
                      </SelectTrigger>
                      <SelectContent>
                        {strategies.map(s => (
                          <SelectItem key={s.key} value={s.key}>{s.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label>Years Back</Label>
                      <Input 
                        type="number" 
                        value={years} 
                        onChange={(e) => setYears(Number(e.target.value))}
                        min={1} max={25}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label>Initial Capital ($)</Label>
                      <Input 
                        type="number" 
                        value={initialCash} 
                        onChange={(e) => setInitialCash(Number(e.target.value))}
                      />
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="pt-4">
                    <Button 
                      onClick={runBacktest}
                      disabled={loading}
                      className="w-full gap-2"
                    >
                      {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                      Run System Backtest
                    </Button>
                  </div>
                </CardContent>
              </Card>

              {/* Strategy Info */}
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Strategy Information</CardTitle>
                </CardHeader>
                <CardContent>
                  {strategies.find(s => s.key === selectedStrategy) && (
                    <div className="space-y-4">
                      <div>
                        <h4 className="text-sm font-semibold mb-1">Benchmark Ticker</h4>
                        <Badge>{strategies.find(s => s.key === selectedStrategy)?.ticker}</Badge>
                      </div>
                      <div>
                        <h4 className="text-sm font-semibold mb-1">Required Market Data</h4>
                        <div className="flex gap-2 flex-wrap">
                          {strategies.find(s => s.key === selectedStrategy)?.tickers_needed.map(t => (
                            <Badge key={t} variant="outline">{t}</Badge>
                          ))}
                        </div>
                      </div>
                      <div className="bg-slate-100 p-4 rounded-lg mt-4 text-sm text-slate-600">
                        <p>This will execute a vectorized/event-driven simulation over the requested timeframe. Make sure your local SQLite market data contains the required tickers.</p>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>
          </TabsContent>

          {/* Results Tab */}
          <TabsContent value="results" className="space-y-6">
            {selectedResult ? (
              <>
                <div className="flex justify-between items-end">
                  <div>
                    <h2 className="text-2xl font-bold">{selectedResult.strategy_name}</h2>
                    <p className="text-slate-500">
                      {selectedResult.data_start} to {selectedResult.data_end} • {selectedResult.trading_days} trading days
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-sm text-slate-500">Run ID</p>
                    <p className="font-mono text-sm">{selectedResult.id}</p>
                  </div>
                </div>

                {/* Metrics Cards */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Total Return</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className={`text-2xl font-bold ${selectedResult.metrics.total_return >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {formatPercent(selectedResult.metrics.total_return)}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">vs {formatPercent(selectedResult.metrics.benchmark_total_return)} B&H</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Annualized (CAGR)</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className={`text-2xl font-bold ${selectedResult.metrics.cagr >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {formatPercent(selectedResult.metrics.cagr)}
                      </div>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Max Drawdown</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold text-red-600">
                        {formatPercent(selectedResult.metrics.max_drawdown)}
                      </div>
                      <p className="text-xs text-slate-500 mt-1">vs {formatPercent(selectedResult.metrics.benchmark_max_drawdown)} B&H</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader className="pb-2">
                      <CardDescription>Sharpe Ratio</CardDescription>
                    </CardHeader>
                    <CardContent>
                      <div className="text-2xl font-bold text-blue-600">
                        {selectedResult.metrics.sharpe_ratio?.toFixed(2)}
                      </div>
                    </CardContent>
                  </Card>
                </div>

                {/* Equity Curve Chart */}
                {selectedResult.equity_curve.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Activity className="h-5 w-5" />
                        Equity Curve vs Benchmark
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ResponsiveContainer width="100%" height={400}>
                        <AreaChart data={getChartData()}>
                          <defs>
                            <linearGradient id="colorEquity" x1="0" y1="0" x2="0" y2="1">
                              <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3}/>
                              <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                            </linearGradient>
                          </defs>
                          <CartesianGrid strokeDasharray="3 3" />
                          <XAxis 
                            dataKey="date" 
                            tickFormatter={(val) => new Date(val).toLocaleDateString()}
                          />
                          <YAxis tickFormatter={(val) => `$${(val / 1000).toFixed(0)}k`} />
                          <Tooltip 
                            formatter={(val: number) => formatCurrency(val)}
                            labelFormatter={(label) => new Date(label).toLocaleDateString()}
                          />
                          <Legend />
                          <Area 
                            type="monotone" 
                            dataKey="Portfolio" 
                            stroke="#3b82f6" 
                            fillOpacity={1} 
                            fill="url(#colorEquity)"
                          />
                          <Line 
                            type="monotone" 
                            dataKey="Benchmark" 
                            stroke="#64748b" 
                            dot={false}
                          />
                        </AreaChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                )}

                {/* Trades Table */}
                {selectedResult.trades.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle>Trade Execution History</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ScrollArea className="h-[400px]">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Date</TableHead>
                              <TableHead>Ticker</TableHead>
                              <TableHead>Action</TableHead>
                              <TableHead>Qty</TableHead>
                              <TableHead>Price</TableHead>
                              <TableHead>P&L</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {selectedResult.trades.map((trade, idx) => (
                              <TableRow key={idx}>
                                <TableCell>{new Date(trade.date).toLocaleDateString()}</TableCell>
                                <TableCell className="font-semibold">{trade.ticker}</TableCell>
                                <TableCell>
                                  <Badge variant={trade.action.includes('BUY') ? 'default' : 'secondary'}>
                                    {trade.action}
                                  </Badge>
                                </TableCell>
                                <TableCell>{trade.quantity}</TableCell>
                                <TableCell>{trade.price ? `$${trade.price.toFixed(2)}` : '-'}</TableCell>
                                <TableCell className={trade.pnl > 0 ? 'text-green-600' : trade.pnl < 0 ? 'text-red-600' : ''}>
                                  {trade.pnl !== 0 ? `$${trade.pnl.toFixed(2)}` : '-'}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </ScrollArea>
                    </CardContent>
                  </Card>
                )}
              </>
            ) : (
              <Card className="p-12 text-center">
                <Activity className="h-12 w-12 mx-auto text-slate-300 mb-4" />
                <h3 className="text-lg font-medium text-slate-900 mb-2">No Results Loaded</h3>
                <p className="text-slate-500 mb-4">Run a backtest or select one from history to see results here</p>
                <Button onClick={() => setActiveTab('backtest')} variant="outline">
                  Go to Backtest
                </Button>
              </Card>
            )}
          </TabsContent>

          {/* History Tab */}
          <TabsContent value="history">
            <Card>
              <CardHeader>
                <CardTitle>Database Records</CardTitle>
                <CardDescription>Comprehensive history of all unified backtest executions</CardDescription>
              </CardHeader>
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Run ID</TableHead>
                      <TableHead>Date Executed</TableHead>
                      <TableHead>Strategy</TableHead>
                      <TableHead>Period</TableHead>
                      <TableHead>Return</TableHead>
                      <TableHead>Sharpe</TableHead>
                      <TableHead>Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {backtests.map((bt) => (
                      <TableRow key={bt.id}>
                        <TableCell className="font-mono text-xs text-slate-500">{bt.id.substring(0,8)}</TableCell>
                        <TableCell>{new Date(bt.created_at).toLocaleString()}</TableCell>
                        <TableCell>
                          <Badge variant="outline">{bt.strategy_name}</Badge>
                        </TableCell>
                        <TableCell>{bt.years} yrs ({bt.data_start} to {bt.data_end})</TableCell>
                        <TableCell className={bt.total_return >= 0 ? 'text-green-600 font-medium' : 'text-red-600 font-medium'}>
                          {formatPercent(bt.total_return)}
                        </TableCell>
                        <TableCell>{bt.sharpe_ratio?.toFixed(2) || '-'}</TableCell>
                        <TableCell>
                          <Button 
                            variant="default" 
                            size="sm"
                            disabled={loading}
                            onClick={() => loadBacktestDetails(bt.id)}
                          >
                            Load Details <ChevronRight className="h-4 w-4 ml-1" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {backtests.length === 0 && (
                  <div className="text-center py-12 text-slate-500">
                    No backtest history found in SQLite database.
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  );
}

export default App;
