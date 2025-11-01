import { useEffect, useState } from 'react'
import { Plus, Trash2, Play } from 'lucide-react'
import api from '../api/client'

interface Tunnel {
  id: string
  name: string
  core: string
  type: string
  node_id: string
  spec: Record<string, any>
  quota_mb: number
  used_mb: number
  expires_at: string | null
  status: string
  revision: number
  created_at: string
  updated_at: string
}

const Tunnels = () => {
  const [tunnels, setTunnels] = useState<Tunnel[]>([])
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)

  useEffect(() => {
    fetchData()
  }, [])

  const fetchData = async () => {
    try {
      const [tunnelsRes, nodesRes] = await Promise.all([
        api.get('/tunnels'),
        api.get('/nodes'),
      ])
      setTunnels(tunnelsRes.data)
      setNodes(nodesRes.data)
    } catch (error) {
      console.error('Failed to fetch data:', error)
    } finally {
      setLoading(false)
    }
  }

  const applyTunnel = async (id: string) => {
    try {
      await api.post(`/tunnels/${id}/apply`)
      fetchData()
    } catch (error) {
      console.error('Failed to apply tunnel:', error)
      alert('Failed to apply tunnel')
    }
  }

  const deleteTunnel = async (id: string) => {
    if (!confirm('Are you sure you want to delete this tunnel?')) return
    
    try {
      await api.delete(`/tunnels/${id}`)
      fetchData()
    } catch (error) {
      console.error('Failed to delete tunnel:', error)
      alert('Failed to delete tunnel')
    }
  }

  if (loading) {
    return <div className="text-center py-12">Loading...</div>
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-3xl font-bold text-gray-900">Tunnels</h1>
        <button
          onClick={() => setShowAddModal(true)}
          className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors flex items-center gap-2"
        >
          <Plus size={20} />
          Create Tunnel
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {tunnels.map((tunnel) => (
          <div
            key={tunnel.id}
            className="bg-white rounded-lg border border-gray-200 p-6"
          >
            <div className="flex justify-between items-start mb-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-900">{tunnel.name}</h3>
                <p className="text-sm text-gray-500 mt-1">
                  {tunnel.core} / {tunnel.type}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => applyTunnel(tunnel.id)}
                  className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                  title="Apply tunnel"
                >
                  <Play size={18} />
                </button>
                <button
                  onClick={() => deleteTunnel(tunnel.id)}
                  className="p-2 text-red-600 hover:bg-red-50 rounded-lg"
                  title="Delete tunnel"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div>
                <p className="text-xs text-gray-500 mb-1">Status</p>
                <span
                  className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                    tunnel.status === 'active'
                      ? 'bg-green-100 text-green-800'
                      : tunnel.status === 'error'
                      ? 'bg-red-100 text-red-800'
                      : 'bg-gray-100 text-gray-800'
                  }`}
                >
                  {tunnel.status}
                </span>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Usage</p>
                <p className="text-sm font-medium text-gray-900">
                  {tunnel.used_mb.toFixed(2)} MB
                  {tunnel.quota_mb > 0 && ` / ${tunnel.quota_mb} MB`}
                </p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Revision</p>
                <p className="text-sm font-medium text-gray-900">{tunnel.revision}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 mb-1">Expires</p>
                <p className="text-sm font-medium text-gray-900">
                  {tunnel.expires_at
                    ? new Date(tunnel.expires_at).toLocaleDateString()
                    : 'Never'}
                </p>
              </div>
            </div>

            {tunnel.quota_mb > 0 && (
              <div className="mt-4">
                <div className="flex justify-between text-xs text-gray-500 mb-1">
                  <span>Quota Progress</span>
                  <span>
                    {((tunnel.used_mb / tunnel.quota_mb) * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div
                    className="bg-blue-600 h-2 rounded-full"
                    style={{
                      width: `${Math.min((tunnel.used_mb / tunnel.quota_mb) * 100, 100)}%`,
                    }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {showAddModal && (
        <AddTunnelModal
          nodes={nodes}
          onClose={() => setShowAddModal(false)}
          onSuccess={() => {
            setShowAddModal(false)
            fetchData()
          }}
        />
      )}
    </div>
  )
}

interface AddTunnelModalProps {
  nodes: any[]
  onClose: () => void
  onSuccess: () => void
}

const AddTunnelModal = ({ nodes, onClose, onSuccess }: AddTunnelModalProps) => {
  const [formData, setFormData] = useState({
    name: '',
    core: 'xray',
    type: 'tcp',
    node_id: '',
    quota_mb: 0,
    expires_at: '',
    spec: {} as Record<string, any>,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      const payload = {
        ...formData,
        expires_at: formData.expires_at || null,
        spec: getSpecForType(formData.type),
      }
      await api.post('/tunnels', payload)
      onSuccess()
    } catch (error) {
      console.error('Failed to create tunnel:', error)
      alert('Failed to create tunnel')
    }
  }

  const getSpecForType = (type: string): Record<string, any> => {
    const baseSpec: Record<string, any> = {
      listen_port: 10000,
    }

    switch (type) {
      case 'ws':
        return { ...baseSpec, path: '/', uuid: generateUUID() }
      case 'grpc':
        return { ...baseSpec, service_name: 'GrpcService', uuid: generateUUID() }
      case 'wireguard':
        return {
          ...baseSpec,
          private_key: '',
          peer_public_key: '',
          address: '10.0.0.1/24',
          allowed_ips: '0.0.0.0/0',
        }
      case 'rathole':
        return { ...baseSpec, remote_addr: '', token: '', local_addr: '127.0.0.1:8080' }
      default:
        return baseSpec
    }
  }

  const generateUUID = () => {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0
      const v = c === 'x' ? r : (r & 0x3) | 0x8
      return v.toString(16)
    })
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 overflow-auto">
      <div className="bg-white rounded-lg p-6 w-full max-w-2xl my-8">
        <h2 className="text-xl font-bold text-gray-900 mb-4">Create Tunnel</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Node
              </label>
              <select
                value={formData.node_id}
                onChange={(e) => setFormData({ ...formData, node_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                required
              >
                <option value="">Select a node</option>
                {nodes.map((node) => (
                  <option key={node.id} value={node.id}>
                    {node.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Core
              </label>
              <select
                value={formData.core}
                onChange={(e) => setFormData({ ...formData, core: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="xray">Xray</option>
                <option value="wireguard">WireGuard</option>
                <option value="rathole">Rathole</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              >
                <option value="tcp">TCP</option>
                <option value="udp">UDP</option>
                <option value="ws">WebSocket</option>
                <option value="grpc">gRPC</option>
                <option value="wireguard">WireGuard</option>
                <option value="rathole">Rathole</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Quota (MB, 0 = unlimited)
              </label>
              <input
                type="number"
                value={formData.quota_mb}
                onChange={(e) =>
                  setFormData({ ...formData, quota_mb: parseFloat(e.target.value) || 0 })
                }
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
                min="0"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Expires At
              </label>
              <input
                type="datetime-local"
                value={formData.expires_at}
                onChange={(e) => setFormData({ ...formData, expires_at: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg"
              />
            </div>
          </div>

          <div className="flex gap-3 justify-end">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Create Tunnel
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default Tunnels

