import { useEffect, useState } from 'react'
import { Server, Network, Cpu, MemoryStick } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import api from '../api/client'

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
}

const Dashboard = () => {
  const [status, setStatus] = useState<Status | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const response = await api.get('/status')
        setStatus(response.data)
      } catch (error) {
        console.error('Failed to fetch status:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchStatus()
    const interval = setInterval(fetchStatus, 5000)
    return () => {
      clearInterval(interval)
    }
  }, [])

  if (loading || !status) {
    return <div className="text-center py-12">Loading...</div>
  }

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-8">Dashboard</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
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

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">System Resources</h2>
          <div className="space-y-4">
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

        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-4">Quick Actions</h2>
          <div className="space-y-3">
            <button 
              onClick={() => window.location.href = '/tunnels?create=true'}
              className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
            >
              Create New Tunnel
            </button>
            <button 
              onClick={() => window.location.href = '/nodes?add=true'}
              className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
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
    blue: 'bg-blue-100 text-blue-600',
    green: 'bg-green-100 text-green-600',
    purple: 'bg-purple-100 text-purple-600',
    orange: 'bg-orange-100 text-orange-600',
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <div className={`p-3 rounded-lg ${colorClasses[color]}`}>
          <Icon size={24} />
        </div>
      </div>
      <h3 className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">{title}</h3>
      <p className="text-2xl font-bold text-gray-900 dark:text-white">{value}</p>
      <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{subtitle}</p>
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
    purple: 'bg-purple-600',
    orange: 'bg-orange-600',
  }

  return (
    <div>
      <div className="flex justify-between text-sm mb-2">
        <span className="text-gray-700 dark:text-gray-300">{label}</span>
        <span className="text-gray-500 dark:text-gray-400">{value.toFixed(1)}%</span>
      </div>
      <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
        <div
          className={`h-2 rounded-full ${colorClasses[color]}`}
          style={{ width: `${Math.min(value, 100)}%` }}
        />
      </div>
    </div>
  )
}

export default Dashboard

