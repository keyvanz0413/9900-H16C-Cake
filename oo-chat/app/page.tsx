'use client'

import { useCallback, useState } from 'react'
import { useRouter } from 'next/navigation'
import { HiOutlineInbox, HiOutlinePlus, HiOutlineServer, HiOutlineStatusOnline, HiOutlineStatusOffline } from 'react-icons/hi'
import { Chat, type UI } from '@/components/chat'
import { ChatLayout } from '@/components/chat-layout'
import { useChatStore } from '@/store/chat-store'
import { useIdentity } from '@/hooks/use-identity'
import { useAgentInfo, shortAddress } from '@/hooks/use-agent-info'

const USE_DEFAULT_AGENT = process.env.NEXT_PUBLIC_USE_DEFAULT_AGENT === 'true'
const DEFAULT_AGENT_NAME = process.env.NEXT_PUBLIC_DEFAULT_AGENT_NAME || 'Email Agent'

interface DirectChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

export default function Home() {
  if (USE_DEFAULT_AGENT) {
    return <DefaultAgentHome />
  }

  return <AddressBookHome />
}

function DefaultAgentHome() {
  const [ui, setUI] = useState<UI[]>([])
  const [messages, setMessages] = useState<DirectChatMessage[]>([])
  const [agentSession, setAgentSession] = useState<unknown>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [connectionError, setConnectionError] = useState<string | null>(null)
  const [lastUserMessage, setLastUserMessage] = useState('')

  const requestAgentReply = useCallback(async (content: string, history: DirectChatMessage[], session: unknown) => {
    setIsLoading(true)
    setConnectionError(null)

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: content,
          messages: history,
          agentSession: session,
          useDefaultAgent: true,
        }),
      })

      const data = await response.json() as { response?: string; error?: string; session?: unknown }
      if (!response.ok) {
        throw new Error(data.error || 'Failed to reach the email agent.')
      }

      const replyText = data.response || ''
      const assistantMessage: DirectChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: replyText,
      }

      setMessages(prev => [...prev, assistantMessage])
      setUI(prev => [...prev, { id: assistantMessage.id, type: 'agent', content: replyText }])
      setAgentSession(data.session ?? null)
    } catch (error) {
      setConnectionError(error instanceof Error ? error.message : 'Failed to reach the email agent.')
    } finally {
      setIsLoading(false)
    }
  }, [])

  const handleSend = useCallback(async (content: string) => {
    const userMessage: DirectChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
    }
    const nextHistory = [...messages, userMessage]

    setLastUserMessage(content)
    setMessages(nextHistory)
    setUI(prev => [...prev, { id: userMessage.id, type: 'user', content }])

    await requestAgentReply(content, nextHistory, agentSession)
  }, [agentSession, messages, requestAgentReply])

  const handleRetry = useCallback(async () => {
    if (!lastUserMessage) return
    await requestAgentReply(lastUserMessage, messages, agentSession)
  }, [agentSession, lastUserMessage, messages, requestAgentReply])

  const sessionState = isLoading ? 'active' : ui.length > 0 ? 'connected' : 'idle'

  return (
    <ChatLayout>
      <div className="flex flex-1 flex-col min-h-0 bg-white">
        <div className="border-b border-neutral-200 px-6 py-5">
          <div className="mx-auto flex max-w-3xl items-start gap-4">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-neutral-900 text-white">
              <HiOutlineInbox className="h-6 w-6" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h1 className="text-lg font-semibold text-neutral-900">{DEFAULT_AGENT_NAME}</h1>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-xs font-medium text-emerald-700">
                  <HiOutlineServer className="h-3.5 w-3.5" />
                  Docker local mode
                </span>
              </div>
              <p className="mt-1 text-sm text-neutral-500">
                Open the page and chat directly with the bundled email agent. No relay or pasted address needed.
              </p>
            </div>
          </div>
        </div>

        <div className="min-h-0 flex-1">
          <Chat
            ui={ui}
            onSend={handleSend}
            isLoading={isLoading}
            placeholder="Ask your email agent about inbox, replies, meetings, or CRM..."
            sessionState={sessionState}
            connectionError={connectionError || undefined}
            onRetry={connectionError && lastUserMessage ? handleRetry : undefined}
          />
        </div>
      </div>
    </ChatLayout>
  )
}

function AddressBookHome() {
  const router = useRouter()
  const { agents, addAgent } = useChatStore()
  const infoMap = useAgentInfo(agents)
  const [newAddress, setNewAddress] = useState('')
  const [showAddForm, setShowAddForm] = useState(false)

  useIdentity()

  const handleAddAgent = (address: string) => {
    const trimmed = address.trim()
    if (!trimmed) return
    addAgent(trimmed)
    setNewAddress('')
    setShowAddForm(false)
    router.push(`/${trimmed}`)
  }

  // No agents - show welcome + add form
  if (agents.length === 0) {
    return (
      <ChatLayout>
        <div className="flex-1 flex flex-col items-center justify-center p-8">
          <img
            src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png"
            alt="OpenOnion"
            width={64}
            height={64}
            className="mb-6 rounded-2xl shadow-xl shadow-neutral-200"
          />

          <h1 className="mb-2 text-2xl font-bold tracking-tight text-neutral-900">
            Welcome to oo-chat
          </h1>
          <p className="mb-8 max-w-md text-center text-neutral-500">
            Connect to an AI agent to start chatting
          </p>

          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleAddAgent(newAddress)
            }}
            className="w-full max-w-md space-y-3"
          >
            <input
              type="text"
              value={newAddress}
              onChange={(e) => setNewAddress(e.target.value)}
              placeholder="Paste agent address (0x...)"
              autoFocus
              className="w-full px-4 py-3 rounded-xl bg-neutral-50 border border-neutral-200 text-neutral-900 focus:bg-white focus:border-neutral-400 focus:ring-4 focus:ring-neutral-100 outline-none font-mono text-sm transition-all placeholder:text-neutral-400"
            />
            <button
              type="submit"
              disabled={!newAddress.trim()}
              className="w-full px-4 py-3 bg-neutral-900 text-white text-sm font-bold rounded-xl hover:bg-neutral-800 transition-all shadow-lg shadow-neutral-200 active:scale-[0.99] disabled:opacity-30 disabled:cursor-not-allowed"
            >
              Connect
            </button>
          </form>
        </div>
      </ChatLayout>
    )
  }

  // Has agents - show agent picker
  return (
    <ChatLayout>
      <div className="flex-1 flex flex-col items-center justify-center p-8">
        <img
          src="https://raw.githubusercontent.com/wu-changxing/openonion-assets/master/imgs/Onion.png"
          alt="OpenOnion"
          width={64}
          height={64}
          className="mb-6 rounded-2xl shadow-xl shadow-neutral-200"
        />

        <h1 className="mb-2 text-2xl font-bold tracking-tight text-neutral-900">
          Choose an agent
        </h1>
        <p className="mb-8 text-neutral-500">
          Select an agent to start a new conversation
        </p>

        {/* Agent Grid */}
        <div className="w-full max-w-lg space-y-2 mb-6">
          {agents.map(address => {
            const info = infoMap[address]
            const label = info?.name || shortAddress(address)
            return (
              <button
                key={address}
                onClick={() => router.push(`/${address}`)}
                className="w-full flex items-center gap-4 p-4 rounded-xl bg-white border border-neutral-200 hover:border-neutral-300 hover:shadow-md transition-all text-left group"
              >
                <div className="w-12 h-12 rounded-xl bg-neutral-900 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform">
                  <span className="text-white font-bold text-lg">
                    {label.charAt(0).toUpperCase()}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-neutral-900">{label}</span>
                    {info?.online !== undefined && (
                      info.online
                        ? <HiOutlineStatusOnline className="w-4 h-4 text-green-500" />
                        : <HiOutlineStatusOffline className="w-4 h-4 text-neutral-400" />
                    )}
                  </div>
                  <span className="text-xs text-neutral-400 font-mono">{shortAddress(address)}</span>
                </div>
              </button>
            )
          })}
        </div>

        {/* Add Agent */}
        {showAddForm ? (
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleAddAgent(newAddress)
            }}
            className="w-full max-w-lg flex gap-2"
          >
            <input
              type="text"
              value={newAddress}
              onChange={(e) => setNewAddress(e.target.value)}
              placeholder="0x..."
              autoFocus
              onBlur={() => { if (!newAddress.trim()) setShowAddForm(false) }}
              className="flex-1 px-4 py-3 rounded-xl bg-neutral-50 border border-neutral-200 text-neutral-900 focus:bg-white focus:border-neutral-400 outline-none font-mono text-sm transition-all placeholder:text-neutral-400"
            />
            <button
              type="submit"
              disabled={!newAddress.trim()}
              className="px-6 py-3 bg-neutral-900 text-white text-sm font-bold rounded-xl hover:bg-neutral-800 transition-all disabled:opacity-30"
            >
              Add
            </button>
          </form>
        ) : (
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm text-neutral-500 hover:text-neutral-700 hover:bg-neutral-100 transition-all"
          >
            <HiOutlinePlus className="w-4 h-4" />
            Add another agent
          </button>
        )}
      </div>
    </ChatLayout>
  )
}
