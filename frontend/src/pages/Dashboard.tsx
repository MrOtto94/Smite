import { useEffect, useState } from 'react'
import { Server, Network, Cpu, MemoryStick, Plus, Activity as ActivityIcon, TrendingUp } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import api from '../api/client'
import { formatTraffic, formatTrafficRate } from '../utils/formatTraffic'

interface Status {
  system: {
    cpu_percent: number
    memory_percent: number
    memory_total_gb: number
    memory_used_gb: number
  }
  tunnels: {
    total: number
    active: number
  }
  nodes: {
    total: number
    active: number
  }
  traffic: {
    total_mb: number
    total_bytes: number
    current_rate_mb_per_hour: number
  }
}


interface TrafficDataPoint {
  timestamp: string
  bytes: number
  mb: number
}

const Dashboard = () => {
  const [status, setStatus] = useState<Status | null>(null)
  const [trafficData, setTrafficData] = useState<TrafficDataPoint[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [statusResponse, statsResponse] = await Promise.all([
          api.get('/status'),
          api.get('/usage/stats?hours=24')
        ])
        setStatus(statusResponse.data)
        setTrafficData(statsResponse.data.time_series || [])
      } catch (error) {
        console.error('Failed to fetch data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => {
      clearInterval(interval)
    }
  }, [])

  if (loading || !status) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 dark:border-blue-400 mb-4"></div>
          <p className="text-gray-500 dark:text-gray-400">Loading dashboard...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="w-full max-w-7xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">Dashboard</h1>
        <p className="text-gray-500 dark:text-gray-400">Overview of your system status and resources</p>
      </div>

      {/* Traffic Summary Box */}
      {status?.traffic && (
        <div className="mb-8 bg-gradient-to-r from-blue-600 to-indigo-600 dark:from-blue-700 dark:to-indigo-700 rounded-xl shadow-lg border border-blue-500 dark:border-blue-600 p-6">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="p-3 bg-white/20 rounded-lg backdrop-blur-sm">
                <TrendingUp className="w-8 h-8 text-white" />
              </div>
              <div>
                <h2 className="text-sm font-medium text-blue-100 mb-1">Total Traffic</h2>
                <p className="text-3xl font-bold text-white">
                  {formatTraffic(status.traffic.total_mb)}
                </p>
                <p className="text-sm text-blue-100 mt-1">
                  Current rate: {formatTrafficRate(status.traffic.current_rate_mb_per_hour)}
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="Total Nodes"
          value={status.nodes.total}
          subtitle={`${status.nodes.active} active`}
          icon={Server}
          color="blue"
        />
        <StatCard
          title="Total Tunnels"
          value={status.tunnels.total}
          subtitle={`${status.tunnels.active} active`}
          icon={Network}
          color="green"
        />
        <StatCard
          title="CPU Usage"
          value={`${status.system.cpu_percent.toFixed(1)}%`}
          subtitle="Current usage"
          icon={Cpu}
          color="purple"
        />
        <StatCard
          title="Memory Usage"
          value={`${status.system.memory_used_gb.toFixed(1)} GB`}
          subtitle={`${status.system.memory_percent.toFixed(1)}% of ${status.system.memory_total_gb.toFixed(1)} GB`}
          icon={MemoryStick}
          color="orange"
        />
      </div>


      {/* Traffic Chart */}
      {trafficData.length > 0 && (
        <div className="mb-8 bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <TrendingUp className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Traffic Chart</h2>
          </div>
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={trafficData.map((item, index) => ({ ...item, index }))}>
              <defs>
                <linearGradient id="colorTraffic" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.8}/>
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0}/>
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" className="opacity-30" />
              <XAxis 
                dataKey="index" 
                tick={{ fill: '#6b7280', fontSize: 12 }}
                className="dark:text-gray-400"
                hide
              />
              <YAxis 
                tick={{ fill: '#6b7280', fontSize: 12 }}
                className="dark:text-gray-400"
                tickFormatter={(value) => formatTraffic(value)}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: '#1f2937', 
                  border: '1px solid #374151',
                  borderRadius: '8px',
                  color: '#fff'
                }}
                formatter={(value: number) => formatTraffic(value)}
                labelFormatter={() => ''}
              />
              <Area 
                type="monotone" 
                dataKey="mb" 
                stroke="#3b82f6" 
                fillOpacity={1} 
                fill="url(#colorTraffic)" 
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Bottom Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* System Resources Card */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <ActivityIcon className="w-5 h-5 text-purple-600 dark:text-purple-400" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">System Resources</h2>
          </div>
          <div className="space-y-5">
            <ProgressBar
              label="CPU"
              value={status.system.cpu_percent}
              color="purple"
            />
            <ProgressBar
              label="Memory"
              value={status.system.memory_percent}
              color="orange"
            />
          </div>
        </div>

        {/* Quick Actions Card */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6 transition-shadow hover:shadow-md">
          <div className="flex items-center gap-3 mb-6">
            <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Plus className="w-5 h-5 text-blue-600 dark:text-blue-400" />
            </div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">Quick Actions</h2>
          </div>
          <div className="space-y-3">
            <button 
              onClick={() => window.location.href = '/tunnels?create=true'}
              className="w-full px-4 py-3 bg-gradient-to-r from-blue-600 to-indigo-600 text-white rounded-lg hover:from-blue-700 hover:to-indigo-700 transition-all duration-200 font-medium shadow-sm hover:shadow-md"
            >
              Create New Tunnel
            </button>
            <button 
              onClick={() => window.location.href = '/nodes?add=true'}
              className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-all duration-200 font-medium border border-gray-200 dark:border-gray-600"
            >
              Add Node
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

interface StatCardProps {
  title: string
  value: string | number
  subtitle: string
  icon: LucideIcon
  color: 'blue' | 'green' | 'purple' | 'orange'
}

const StatCard = ({ title, value, subtitle, icon: Icon, color }: StatCardProps) => {
  const colorClasses = {
    blue: {
      bg: 'bg-blue-50 dark:bg-blue-900/20',
      icon: 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400',
      accent: 'bg-blue-500'
    },
    green: {
      bg: 'bg-green-50 dark:bg-green-900/20',
      icon: 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400',
      accent: 'bg-green-500'
    },
    purple: {
      bg: 'bg-purple-50 dark:bg-purple-900/20',
      icon: 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400',
      accent: 'bg-purple-500'
    },
    orange: {
      bg: 'bg-orange-50 dark:bg-orange-900/20',
      icon: 'bg-orange-100 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400',
      accent: 'bg-orange-500'
    },
  }

  const colors = colorClasses[color]

  return (
    <div className={`relative bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-5 transition-all duration-200 hover:shadow-md ${colors.bg}`}>
      <div className="flex items-start justify-between mb-3">
        <div className={`p-3 rounded-lg ${colors.icon} transition-transform hover:scale-110`}>
          <Icon className="w-6 h-6" />
        </div>
      </div>
      <h3 className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-1.5">{title}</h3>
      <p className="text-3xl font-bold text-gray-900 dark:text-white mb-1">{value}</p>
      <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
      <div className={`absolute bottom-0 left-0 right-0 h-1 ${colors.accent} rounded-b-xl`}></div>
    </div>
  )
}

interface ProgressBarProps {
  label: string
  value: number
  color: 'purple' | 'orange'
}

const ProgressBar = ({ label, value, color }: ProgressBarProps) => {
  const colorClasses = {
    purple: {
      bg: 'bg-purple-600 dark:bg-purple-500',
      gradient: 'from-purple-500 to-purple-600'
    },
    orange: {
      bg: 'bg-orange-600 dark:bg-orange-500',
      gradient: 'from-orange-500 to-orange-600'
    },
  }

  const colors = colorClasses[color]
  const percentage = Math.min(value, 100)

  return (
    <div>
      <div className="flex justify-between items-center text-sm mb-2.5">
        <span className="font-medium text-gray-700 dark:text-gray-300">{label}</span>
        <span className="font-semibold text-gray-900 dark:text-white">{value.toFixed(1)}%</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2.5 overflow-hidden">
        <div
          className={`h-2.5 rounded-full bg-gradient-to-r ${colors.gradient} transition-all duration-500 ease-out`}
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  )
}

export default Dashboard
