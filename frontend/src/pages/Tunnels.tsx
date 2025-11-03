import { useEffect, useState } from 'react'
import { Plus, Trash2, Edit2 } from 'lucide-react'
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
  error_message?: string | null
  revision: number
  created_at: string
  updated_at: string
}

const Tunnels = () => {
  const [tunnels, setTunnels] = useState<Tunnel[]>([])
  const [nodes, setNodes] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showAddModal, setShowAddModal] = useState(false)
  const [editingTunnel, setEditingTunnel] = useState<Tunnel | null>(null)

  useEffect(() => {
    fetchData()
    // Check if we should open the modal from URL params
    const params = new URLSearchParams(window.location.search)
    if (params.get('create') === 'true') {
      setShowAddModal(true)
      // Clean URL
      window.history.replaceState({}, '', '/tunnels')
    }
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
            className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4"
          >
            <div className="flex justify-between items-start mb-2">
              <div>
                <h3 className="text-base font-semibold text-gray-900 dark:text-white">{tunnel.name}</h3>
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                  {tunnel.core} / {tunnel.type}
                </p>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => setEditingTunnel(tunnel)}
                  className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg"
                  title="Edit tunnel"
                >
                  <Edit2 size={18} />
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

            {tunnel.status === 'error' && tunnel.error_message && (
              <div className="mb-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                <p className="text-xs font-medium text-red-800 dark:text-red-200 mb-1">Error</p>
                <p className="text-sm text-red-700 dark:text-red-300">{tunnel.error_message}</p>
              </div>
            )}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-2">
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Status</p>
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
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Usage</p>
                <div className="space-y-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {tunnel.quota_mb > 0 
                      ? `${tunnel.used_mb.toFixed(2)} MB / ${(tunnel.quota_mb / 1024).toFixed(0)} GB`
                      : `${tunnel.used_mb.toFixed(2)} MB`
                    }
                  </p>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all"
                      style={{ 
                        width: tunnel.quota_mb > 0 
                          ? `${Math.min((tunnel.used_mb / tunnel.quota_mb) * 100, 100)}%`
                          : tunnel.used_mb > 0 
                            ? '100%'
                            : '0%'
                      }}
                    />
                  </div>
                </div>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Revision</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">{tunnel.revision}</p>
              </div>
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Expires</p>
                <p className="text-sm font-medium text-gray-900 dark:text-white">
                  {tunnel.expires_at
                    ? new Date(tunnel.expires_at).toLocaleDateString()
                    : 'Never'}
                </p>
              </div>
            </div>
            
            {/* Port Details */}
            <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                <div>
                  <p className="text-gray-500 dark:text-gray-400 mb-1">Proxy Port</p>
                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                    {tunnel.spec?.remote_port || tunnel.spec?.listen_port || 'N/A'}
                  </p>
                </div>
                {tunnel.core === 'rathole' && (
                  <>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400 mb-1">Rathole Port</p>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {tunnel.spec?.remote_addr ? tunnel.spec.remote_addr.split(':')[1] : 'N/A'}
                      </p>
                    </div>
                    <div>
                      <p className="text-gray-500 dark:text-gray-400 mb-1">Local Port</p>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {tunnel.spec?.local_addr ? tunnel.spec.local_addr.split(':')[1] : 'N/A'}
                      </p>
                    </div>
                  </>
                )}
                {tunnel.core === 'xray' && tunnel.spec?.forward_to && (
                  <div>
                    <p className="text-gray-500 dark:text-gray-400 mb-1">Forward To</p>
                    <p className="text-sm font-medium text-gray-900 dark:text-white">
                      {tunnel.spec.forward_to}
                    </p>
                  </div>
                )}
              </div>
            </div>

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

      {editingTunnel && (
        <EditTunnelModal
          tunnel={editingTunnel}
          nodes={nodes}
          onClose={() => setEditingTunnel(null)}
          onSuccess={() => {
            setEditingTunnel(null)
            fetchData()
          }}
        />
      )}
    </div>
  )
}

interface EditTunnelModalProps {
  tunnel: Tunnel
  nodes: any[]
  onClose: () => void
  onSuccess: () => void
}

const EditTunnelModal = ({ tunnel, onClose, onSuccess }: EditTunnelModalProps) => {
  const [formData, setFormData] = useState({
    name: tunnel.name,
    quota_mb: tunnel.quota_mb,
    expires_days: '',
    expires_date: tunnel.expires_at ? tunnel.expires_at.split('T')[0] : '',
    remote_port: tunnel.spec?.remote_port || tunnel.spec?.listen_port || 10000,
    forward_port: tunnel.spec?.forward_to ? tunnel.spec.forward_to.split(':')[1] : '',
    rathole_remote_addr: tunnel.spec?.remote_addr || '',
    rathole_local_port: tunnel.spec?.local_addr ? tunnel.spec.local_addr.split(':')[1] : '',
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      let expires_at: string | null = null
      if (formData.expires_days) {
        const days = parseInt(formData.expires_days)
        if (days > 0) {
          const expiryDate = new Date()
          expiryDate.setDate(expiryDate.getDate() + days)
          expires_at = expiryDate.toISOString().split('T')[0] + 'T00:00:00'
        }
      } else if (formData.expires_date) {
        expires_at = formData.expires_date + 'T00:00:00'
      }

      // Build updated spec
      const updatedSpec = { ...tunnel.spec }
      updatedSpec.remote_port = parseInt(formData.remote_port.toString()) || 10000
      
      if (tunnel.core === 'rathole') {
        if (formData.rathole_remote_addr) {
          const remoteParts = formData.rathole_remote_addr.split(':')
          const remoteHost = remoteParts[0] || window.location.hostname
          const remotePort = remoteParts[1] || '23333'
          updatedSpec.remote_addr = `${remoteHost}:${remotePort}`
        }
        if (formData.rathole_local_port) {
          updatedSpec.local_addr = `127.0.0.1:${formData.rathole_local_port}`
        }
      } else if (tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'ws' || tunnel.type === 'grpc')) {
        if (formData.forward_port) {
          updatedSpec.forward_to = `127.0.0.1:${formData.forward_port}`
        }
      }

      await api.put(`/tunnels/${tunnel.id}`, {
        name: formData.name,
        quota_mb: formData.quota_mb,
        expires_at: expires_at,
        spec: updatedSpec,
      })
      onSuccess()
    } catch (error) {
      console.error('Failed to update tunnel:', error)
      alert('Failed to update tunnel')
    }
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-md">
        <h2 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Edit Tunnel</h2>
        <form onSubmit={handleSubmit} className="space-y-4">
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
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Quota (MB, 0 = unlimited)
            </label>
            <input
              type="number"
              value={formData.quota_mb}
              onChange={(e) =>
                setFormData({ ...formData, quota_mb: parseFloat(e.target.value) || 0 })
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
              min="0"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
              Proxy Port
            </label>
            <input
              type="number"
              value={formData.remote_port}
              onChange={(e) =>
                setFormData({ ...formData, remote_port: parseInt(e.target.value) || 10000 })
              }
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
              min="1"
              max="65535"
            />
          </div>
          
          {tunnel.core === 'rathole' && (
            <>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="text"
                  value={formData.rathole_remote_addr}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_remote_addr: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder={`${window.location.hostname}:23333`}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                />
              </div>
            </>
          )}
          
          {tunnel.core === 'xray' && (tunnel.type === 'tcp' || tunnel.type === 'ws' || tunnel.type === 'grpc') && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Xray Panel Port
              </label>
              <input
                type="number"
                value={formData.forward_port}
                onChange={(e) =>
                  setFormData({ ...formData, forward_port: e.target.value })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                placeholder="2053"
                min="1"
                max="65535"
              />
            </div>
          )}
          
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Expires In (days)
              </label>
              <input
                type="number"
                value={formData.expires_days}
                onChange={(e) => {
                  const days = e.target.value
                  setFormData({ ...formData, expires_days: days, expires_date: '' })
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="1"
                placeholder="e.g., 30"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Or Expires On (date)
              </label>
              <input
                type="date"
                value={formData.expires_date}
                onChange={(e) => {
                  const date = e.target.value
                  setFormData({ ...formData, expires_date: date, expires_days: '' })
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min={new Date().toISOString().split('T')[0]}
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
              Save Changes
            </button>
          </div>
        </form>
      </div>
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
    expires_days: '',
    expires_date: '',
    remote_port: 10000,
    forward_to: '127.0.0.1:2053',
    forward_port: '2053',
    rathole_remote_addr: `${window.location.hostname}:23333`,
    rathole_token: '',
    rathole_local_port: '8080',
    spec: {} as Record<string, any>,
  })

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    try {
      // Calculate expires_at from days or date
      let expires_at: string | null = null
      if (formData.expires_days) {
        const days = parseInt(formData.expires_days)
        if (days > 0) {
          const expiryDate = new Date()
          expiryDate.setDate(expiryDate.getDate() + days)
          expires_at = expiryDate.toISOString().split('T')[0] + 'T00:00:00'
        }
      } else if (formData.expires_date) {
        expires_at = formData.expires_date + 'T00:00:00'
      }

      const spec = getSpecForType(formData.core, formData.type)
      spec.remote_port = parseInt(formData.remote_port.toString()) || 10000
      
      // For TCP/WS/gRPC tunnels, add forward_to if specified (always use 127.0.0.1:port)
      if (formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'ws' || formData.type === 'grpc')) {
        const forwardPort = formData.forward_port || (formData.forward_to ? formData.forward_to.split(':')[1] : '2053')
        if (forwardPort) {
          spec.forward_to = `127.0.0.1:${forwardPort}`
        }
      }
      
      // For Rathole, add required fields
      if (formData.core === 'rathole') {
        // Parse rathole_remote_addr to get IP and port
        const remoteParts = formData.rathole_remote_addr.split(':')
        const remoteHost = remoteParts[0] || window.location.hostname
        const remotePort = remoteParts[1] || '23333'
        spec.remote_addr = `${remoteHost}:${remotePort}`
        spec.token = formData.rathole_token
        spec.local_addr = `127.0.0.1:${formData.rathole_local_port}`
        spec.remote_port = parseInt(formData.remote_port.toString()) || 10000  // Proxy port for clients
      }
      
      const payload = {
        name: formData.name,
        core: formData.core,
        type: formData.type,
        node_id: formData.node_id,
        quota_mb: formData.quota_mb,
        expires_at: expires_at,
        spec: spec,
      }
      await api.post('/tunnels', payload)
      onSuccess()
    } catch (error) {
      console.error('Failed to create tunnel:', error)
      alert('Failed to create tunnel')
    }
  }

  const getSpecForType = (core: string, type: string): Record<string, any> => {
    const baseSpec: Record<string, any> = {
      listen_port: 10000,
    }

    // WireGuard and Rathole are separate cores, not types
    if (core === 'wireguard') {
      return {
        ...baseSpec,
        private_key: '',
        peer_public_key: '',
        address: '10.0.0.1/24',
        allowed_ips: '0.0.0.0/0',
      }
    }
    
    if (core === 'rathole') {
      return { ...baseSpec, remote_addr: `${window.location.hostname}:23333`, token: '', local_addr: '127.0.0.1:8080' }
    }

    // Xray core types
    switch (type) {
      case 'ws':
        return { ...baseSpec, path: '/', uuid: generateUUID() }
      case 'grpc':
        return { ...baseSpec, service_name: 'GrpcService', uuid: generateUUID() }
      case 'udp':
        return { ...baseSpec, uuid: generateUUID(), header_type: 'none' }
      default:
        return baseSpec
    }
  }

  // When core changes, update type accordingly
  const handleCoreChange = (core: string) => {
    let newType = formData.type
    if (core === 'wireguard' || core === 'rathole') {
      newType = core // Type matches core for these
    } else if (formData.type === 'wireguard' || formData.type === 'rathole') {
      newType = 'tcp' // Reset to default xray type
    }
    setFormData({ ...formData, core, type: newType })
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
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Name
              </label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                required
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Node
              </label>
              <select
                value={formData.node_id}
                onChange={(e) => setFormData({ ...formData, node_id: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
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
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Core
              </label>
              <select
                value={formData.core}
                onChange={(e) => handleCoreChange(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
              >
                <option value="xray">Xray</option>
                <option value="rathole">Rathole</option>
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Type
              </label>
              <select
                value={formData.type}
                onChange={(e) => setFormData({ ...formData, type: e.target.value })}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                disabled={formData.core === 'wireguard' || formData.core === 'rathole'}
              >
                {(formData.core === 'wireguard' || formData.core === 'rathole') ? (
                  <option value={formData.core}>{formData.core.charAt(0).toUpperCase() + formData.core.slice(1)}</option>
                ) : (
                  <>
                    <option value="tcp">TCP</option>
                    <option value="udp">UDP</option>
                    <option value="ws">WebSocket</option>
                    <option value="grpc">gRPC</option>
                  </>
                )}
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Proxy Port
              </label>
              <input
                type="number"
                value={formData.remote_port}
                onChange={(e) =>
                  setFormData({ ...formData, remote_port: parseInt(e.target.value) || 10000 })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="1"
                max="65535"
                required
              />
              <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                {formData.core === 'rathole' 
                  ? 'Port on panel for clients to connect (should match local service port)'
                  : 'Port on node to listen for connections'}
              </p>
            </div>
            {formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'ws' || formData.type === 'grpc') && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Xray Panel Port
                </label>
                <input
                  type="number"
                  value={formData.forward_port || (formData.forward_to ? formData.forward_to.split(':')[1] : '2053')}
                  onChange={(e) => {
                    const port = e.target.value || '2053'
                    setFormData({ ...formData, forward_port: port, forward_to: `127.0.0.1:${port}` })
                  }}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="2053"
                  min="1"
                  max="65535"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                  {formData.type === 'tcp' 
                    ? 'Xray panel port (e.g., 3x-ui port)' 
                    : 'Leave empty for VMESS server, or enter port to forward to local service'}
                </p>
              </div>
            )}
            {(!(formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'ws' || formData.type === 'grpc'))) && formData.core !== 'rathole' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Quota (MB, 0 = unlimited)
                </label>
                <input
                  type="number"
                  value={formData.quota_mb}
                  onChange={(e) =>
                    setFormData({ ...formData, quota_mb: parseFloat(e.target.value) || 0 })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  min="0"
                />
              </div>
            )}
            {formData.core === 'rathole' && (
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Rathole Port
                </label>
                <input
                  type="text"
                  value={formData.rathole_remote_addr}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_remote_addr: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder={`${window.location.hostname}:23333`}
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Panel IP:Port for rathole server (e.g., {window.location.hostname}:23333)</p>
              </div>
            )}
          </div>
          
          {formData.core === 'xray' && (formData.type === 'tcp' || formData.type === 'ws' || formData.type === 'grpc') && (
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Quota (MB, 0 = unlimited)
              </label>
              <input
                type="number"
                value={formData.quota_mb}
                onChange={(e) =>
                  setFormData({ ...formData, quota_mb: parseFloat(e.target.value) || 0 })
                }
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="0"
              />
            </div>
          )}
          
          {formData.core === 'rathole' && (
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Token
                </label>
                <input
                  type="text"
                  value={formData.rathole_token}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_token: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="your-token"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Authentication token</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Local Port
                </label>
                <input
                  type="number"
                  value={formData.rathole_local_port}
                  onChange={(e) =>
                    setFormData({ ...formData, rathole_local_port: e.target.value })
                  }
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                  placeholder="8080"
                  min="1"
                  max="65535"
                  required
                />
                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Local service port (127.0.0.1:{formData.rathole_local_port || '8080'})</p>
              </div>
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Expires In (days)
              </label>
              <input
                type="number"
                value={formData.expires_days}
                onChange={(e) => {
                  const days = e.target.value
                  setFormData({ ...formData, expires_days: days, expires_date: '' })
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min="1"
                placeholder="e.g., 30"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                Or Expires On (date)
              </label>
              <input
                type="date"
                value={formData.expires_date}
                onChange={(e) => {
                  const date = e.target.value
                  setFormData({ ...formData, expires_date: date, expires_days: '' })
                }}
                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg dark:bg-gray-700 dark:text-white"
                min={new Date().toISOString().split('T')[0]}
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

