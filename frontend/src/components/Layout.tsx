import { ReactNode, useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LayoutDashboard, Network, Settings, FileText, Activity, Moon, Sun, Github } from 'lucide-react'
import SmiteLogoDark from '../assets/SmiteD.png'
import SmiteLogoLight from '../assets/SmiteL.png'

interface LayoutProps {
  children: ReactNode
}

const Layout = ({ children }: LayoutProps) => {
  const location = useLocation()
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem('darkMode')
    return saved ? JSON.parse(saved) : false
  })

  useEffect(() => {
    localStorage.setItem('darkMode', JSON.stringify(darkMode))
    if (darkMode) {
      document.documentElement.classList.add('dark')
    } else {
      document.documentElement.classList.remove('dark')
    }
  }, [darkMode])
  
  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/nodes', label: 'Nodes', icon: Network },
    { path: '/tunnels', label: 'Tunnels', icon: Activity },
    { path: '/logs', label: 'Logs', icon: FileText },
    { path: '/settings', label: 'Settings', icon: Settings },
  ]

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <div className="flex h-screen">
        {/* Sidebar */}
        <aside className="w-64 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col">
          <div className="p-6 border-b border-gray-200 dark:border-gray-700">
            <div className="flex flex-col items-center gap-3 mb-4">
              <img 
                src={darkMode ? SmiteLogoDark : SmiteLogoLight} 
                alt="Smite Logo" 
                className="h-16 w-16"
              />
              <div className="text-center">
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Smite</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Control Panel</p>
              </div>
            </div>
            <div className="flex justify-end">
              <button
                onClick={() => setDarkMode(!darkMode)}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300"
                title={darkMode ? 'Light mode' : 'Dark mode'}
              >
                {darkMode ? <Sun size={20} /> : <Moon size={20} />}
              </button>
            </div>
          </div>
          
          <nav className="flex-1 p-4 space-y-1">
            {navItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                      : 'text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                  }`}
                >
                  <Icon size={20} />
                  <span className="font-medium">{item.label}</span>
                </Link>
              )
            })}
          </nav>
          
          {/* Footer */}
          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex flex-col items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
              <div className="flex items-center gap-1">
                <span>Made with</span>
                <span className="text-red-500">❤️</span>
                <span>by</span>
                <a 
                  href="https://github.com/zZedix" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-blue-600 dark:text-blue-400 hover:underline"
                >
                  zZedix
                </a>
              </div>
              <div className="flex items-center gap-2">
                <span>v0.1.0</span>
                <a 
                  href="https://github.com/zZedix/Smite" 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
                  title="GitHub Repository"
                >
                  <Github size={16} />
                </a>
              </div>
            </div>
          </div>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto bg-gray-50 dark:bg-gray-900">
          <div className="p-8">
            {children}
          </div>
        </main>
      </div>
    </div>
  )
}

export default Layout

