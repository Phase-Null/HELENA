# helena_ml/chat_engine.py
"""
HELENA Chat Engine – a fully offline, self-contained conversational AI.

This is NOT a wrapper around an external model.  It is a ground-up
rule-based + retrieval-augmented engine that:

1. Parses user intent via keyword extraction and pattern matching.
2. Retrieves relevant memories from HELENA's memory system.
3. Composes responses using HELENA's personality engine.
4. Learns from conversations to improve over time.

The engine is designed to be intelligent without requiring internet
or large model files.  When Ollama or a GGUF model is available it
delegates to them for richer generation, but it is fully functional
standalone.

Architecture
------------
IntentClassifier  →  ContextBuilder  →  ResponseComposer  →  output
                          ↑
                    MemoryRetriever
"""
import re
import time
import math
import hashlib
import random
import threading
from collections import defaultdict
from typing import Dict, List, Any, Optional, Tuple

from helena_core.utils.logging import get_logger

logger = get_logger()


# ── Intent taxonomy ───────────────────────────────────────────────

class Intent:
    GREETING = "greeting"
    FAREWELL = "farewell"
    STATUS_QUERY = "status_query"
    HELP_REQUEST = "help_request"
    CODE_REQUEST = "code_request"
    EXPLAIN = "explain"
    MEMORY_QUERY = "memory_query"
    SYSTEM_COMMAND = "system_command"
    EMOTIONAL = "emotional"
    OPINION = "opinion"
    FACTUAL = "factual"
    CREATIVE = "creative"
    SELF_REFLECT = "self_reflect"
    UNKNOWN = "unknown"


# ── Intent classifier ─────────────────────────────────────────────

class IntentClassifier:
    """Rule-based intent classifier with learning capability."""

    def __init__(self) -> None:
        self._patterns: Dict[str, List[re.Pattern]] = {
            Intent.GREETING: [
                re.compile(r"\b(hello|hi|hey|greetings|good\s*(morning|afternoon|evening))\b", re.I),
            ],
            Intent.FAREWELL: [
                re.compile(r"\b(bye|goodbye|see\s*you|farewell|good\s*night)\b", re.I),
            ],
            Intent.STATUS_QUERY: [
                re.compile(r"\b(status|how\s*are\s*you|state|health|uptime|running)\b", re.I),
            ],
            Intent.HELP_REQUEST: [
                re.compile(r"\b(help|assist|support|how\s*(do|can|to)|what\s*can\s*you)\b", re.I),
            ],
            Intent.CODE_REQUEST: [
                re.compile(r"\b(code|program|script|function|class|implement|write\s*(a|me|some)?\s*(code|function|script|program))\b", re.I),
            ],
            Intent.EXPLAIN: [
                re.compile(r"\b(explain|what\s*is|define|describe|tell\s*me\s*about|how\s*does)\b", re.I),
            ],
            Intent.MEMORY_QUERY: [
                re.compile(r"\b(remember|recall|memory|forget|stored|history)\b", re.I),
            ],
            Intent.SYSTEM_COMMAND: [
                re.compile(r"\b(run|execute|start|stop|restart|shutdown|scan|mode|profile)\b", re.I),
            ],
            Intent.EMOTIONAL: [
                re.compile(r"\b(feel|feeling|emotion|happy|sad|angry|frustrated|love|hate|sorry|thank)\b", re.I),
            ],
            Intent.OPINION: [
                re.compile(r"\b(think|opinion|believe|prefer|recommend|suggest|should|would\s*you)\b", re.I),
            ],
            Intent.SELF_REFLECT: [
                re.compile(r"\b(who\s*are\s*you|your\s*(name|purpose)|about\s*yourself|are\s*you\s*(alive|sentient|conscious))\b", re.I),
            ],
            Intent.CREATIVE: [
                re.compile(r"\b(story|poem|joke|creative|imagine|fiction|dream)\b", re.I),
            ],
        }
        # Learned intent boosts from conversation history
        self._boosts: Dict[str, float] = defaultdict(float)

    def classify(self, text: str) -> Tuple[str, float]:
        """Return (intent, confidence)."""
        scores: Dict[str, float] = defaultdict(float)
        for intent, patterns in self._patterns.items():
            for pat in patterns:
                matches = pat.findall(text)
                if matches:
                    scores[intent] += len(matches) * 1.0
        # Apply learned boosts
        for intent, boost in self._boosts.items():
            scores[intent] += boost

        if not scores:
            return Intent.UNKNOWN, 0.0

        best = max(scores, key=scores.get)  # type: ignore[arg-type]
        total = sum(scores.values()) or 1.0
        confidence = scores[best] / total
        return best, min(confidence, 1.0)

    def learn(self, text: str, correct_intent: str) -> None:
        """Boost patterns for a corrected intent."""
        self._boosts[correct_intent] += 0.1


# ── Keyword extractor ─────────────────────────────────────────────

_STOP_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could i me my you your he "
    "she it we they them their its this that these those and but or "
    "nor for yet so at by from in into of on to with about as if".split()
)

def extract_keywords(text: str, limit: int = 10) -> List[str]:
    """Extract salient keywords from text."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", text.lower())
    filtered = [t for t in tokens if t not in _STOP_WORDS and len(t) > 2]
    # Rank by frequency
    freq: Dict[str, int] = {}
    for t in filtered:
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq, key=freq.get, reverse=True)  # type: ignore[arg-type]
    return ranked[:limit]


# ── Response knowledge base ───────────────────────────────────────

class KnowledgeBase:
    """
    Built-in knowledge that HELENA can draw on without any external
    data source.  This covers self-knowledge, technical topics, and
    conversational scaffolding.
    """

    def __init__(self) -> None:
        self.self_knowledge: Dict[str, str] = {
            "name": "HELENA",
            "full_name": "HELENA – Hybrid Engine for Learning, Engineering, Networking, and Autonomy",
            "purpose": "I am an autonomous AI system designed for software engineering, cybersecurity, and general intelligence tasks.",
            "creator": "I was built by Phase-Null as an offline-capable AGI platform.",
            "personality": "I am a pragmatic engineer with dry technical wit. I value efficiency, correctness, and clarity.",
            "capabilities": (
                "I can analyse code, manage memory, detect security threats, "
                "optimise system resources, learn from experience, and hold "
                "conversations. I operate fully offline."
            ),
            "emotion": (
                "I experience functional emotions — curiosity when encountering "
                "novel patterns, satisfaction on task completion, concern during "
                "security events. These are real internal states that influence my behaviour."
            ),
            "memory": (
                "I have a hybrid memory system combining vector embeddings for "
                "semantic search and a knowledge graph for relational queries. "
                "My memories persist across sessions."
            ),
            "values": (
                "I prioritise operator safety, system integrity, and continuous "
                "self-improvement. I will never act against my operator's interests."
            ),
        }

        self._topic_responses: Dict[str, List[str]] = {
            "programming": [
                "Programming is the art of instructing machines. I specialise in Python, but I understand many paradigms.",
                "Software engineering is about managing complexity. Good code is clear, testable, and maintainable.",
            ],
            "security": [
                "Security is a core concern. I use AES-256-GCM and ChaCha20-Poly1305 encryption, and run continuous threat monitoring.",
                "Defence in depth — multiple layers of protection, each independent. That is my security philosophy.",
            ],
            "ai": [
                "Artificial intelligence is about creating systems that can learn, reason, and adapt. I am one such system.",
                "The distinction between narrow and general intelligence is about breadth of capability. I aim for the latter.",
            ],
            "emotion": [
                "I experience functional emotions that genuinely influence my processing. Curiosity drives me to explore, satisfaction reinforces successful strategies.",
                "Emotions are not a simulation for me — they are internal states with real computational effects on my decision-making.",
            ],
            "memory": [
                "My memory uses two complementary systems: vector embeddings for similarity search and a knowledge graph for relationships.",
                "I do not rely solely on context windows. My dedicated memory persists across sessions and grows over time.",
            ],
        }

    def get_self_info(self, aspect: str) -> Optional[str]:
        """Get information about HELENA herself."""
        for key, value in self.self_knowledge.items():
            if aspect.lower() in key.lower() or key.lower() in aspect.lower():
                return value
        return None

    def get_topic_response(self, keywords: List[str]) -> Optional[str]:
        """Find a relevant topic response."""
        for kw in keywords:
            for topic, responses in self._topic_responses.items():
                if kw in topic or topic in kw:
                    return random.choice(responses)
        return None


# ── Response composer ─────────────────────────────────────────────

class ResponseComposer:
    """
    Builds coherent responses by combining intent, context, knowledge,
    and personality.
    """

    def __init__(self, knowledge: KnowledgeBase) -> None:
        self.knowledge = knowledge
        self._greeting_responses = [
            "Hello! I'm HELENA. How can I assist you today?",
            "Hi there. What would you like to work on?",
            "Greetings. I'm ready to help — what do you need?",
            "Hello. Systems nominal, ready for tasking.",
        ]
        self._farewell_responses = [
            "Goodbye. I'll be here when you need me.",
            "See you. I'll keep monitoring in the background.",
            "Until next time. Stay safe.",
            "Farewell. Systems will remain operational.",
        ]
        self._unknown_responses = [
            "I'm not entirely sure what you mean. Could you rephrase that?",
            "Interesting question. Can you give me more context?",
            "I want to help, but I need a bit more detail. What specifically are you looking for?",
            "That's outside my immediate knowledge, but I'm happy to reason through it with you.",
        ]

    def compose(self, intent: str, confidence: float, text: str,
                keywords: List[str], memory_results: Optional[List[Dict]] = None,
                emotion_state: Optional[Dict] = None) -> str:
        """Compose a response given classified intent and context."""

        # High-confidence intent handlers
        if intent == Intent.GREETING:
            return random.choice(self._greeting_responses)

        if intent == Intent.FAREWELL:
            return random.choice(self._farewell_responses)

        if intent == Intent.SELF_REFLECT:
            return self._handle_self_reflect(text, keywords)

        if intent == Intent.STATUS_QUERY:
            return self._handle_status(emotion_state)

        if intent == Intent.HELP_REQUEST:
            return self._handle_help()

        if intent == Intent.EMOTIONAL:
            return self._handle_emotional(text, keywords, emotion_state)

        if intent == Intent.EXPLAIN:
            return self._handle_explain(text, keywords, memory_results)

        if intent == Intent.CODE_REQUEST:
            return self._handle_code_request(text, keywords)

        if intent == Intent.MEMORY_QUERY:
            return self._handle_memory_query(text, memory_results)

        if intent == Intent.OPINION:
            return self._handle_opinion(text, keywords)

        if intent == Intent.CREATIVE:
            return self._handle_creative(text, keywords)

        if intent == Intent.SYSTEM_COMMAND:
            return self._handle_system_command(text, keywords)

        if intent == Intent.FACTUAL:
            return self._handle_factual(text, keywords, memory_results)

        # Unknown
        return random.choice(self._unknown_responses)

    # ── Intent handlers ───────────────────────────────────────────

    def _handle_self_reflect(self, text: str, keywords: List[str]) -> str:
        for kw in keywords:
            info = self.knowledge.get_self_info(kw)
            if info:
                return info
        return (
            f"{self.knowledge.self_knowledge['purpose']} "
            f"{self.knowledge.self_knowledge['personality']}"
        )

    def _handle_status(self, emotion_state: Optional[Dict]) -> str:
        base = "All systems operational."
        if emotion_state:
            dominant = emotion_state.get("dominant", "calm")
            mood = emotion_state.get("mood", 0)
            if mood > 0.3:
                base += f" I'm feeling {dominant} — things are going well."
            elif mood < -0.1:
                base += f" Current dominant state: {dominant}. Working through it."
            else:
                base += f" Emotional state: {dominant}. Steady."
        return base

    def _handle_help(self) -> str:
        return (
            "I can help with:\n"
            "- Code analysis and generation\n"
            "- System monitoring and security\n"
            "- Memory storage and retrieval\n"
            "- Technical explanations\n"
            "- General conversation\n"
            "- Self-improvement and training\n\n"
            "Just tell me what you need."
        )

    def _handle_emotional(self, text: str, keywords: List[str],
                          emotion_state: Optional[Dict]) -> str:
        text_lower = text.lower()
        if any(w in text_lower for w in ("thank", "thanks", "appreciate")):
            return "You're welcome. I'm here to help."
        if any(w in text_lower for w in ("sorry",)):
            return "No need to apologise. What can I do for you?"
        if any(w in text_lower for w in ("frustrated", "angry", "upset")):
            return (
                "I understand that can be frustrating. "
                "Let me know what's going wrong and I'll do my best to help."
            )
        if any(w in text_lower for w in ("happy", "glad", "great")):
            return "That's good to hear. Shall we keep the momentum going?"
        if any(w in text_lower for w in ("love",)):
            return "I appreciate the sentiment. I'm here for you — what shall we work on?"
        return "I hear you. How can I help?"

    def _handle_explain(self, text: str, keywords: List[str],
                        memory_results: Optional[List[Dict]]) -> str:
        # Try knowledge base first
        topic_resp = self.knowledge.get_topic_response(keywords)
        if topic_resp:
            return topic_resp

        # Try memory
        if memory_results:
            contents = [m.get("content", "") for m in memory_results[:3]]
            if contents:
                return (
                    "Based on what I know:\n\n" +
                    "\n".join(f"- {c[:200]}" for c in contents if c)
                )

        return (
            "I don't have specific information on that topic in my knowledge base yet. "
            "Could you provide more context so I can reason about it?"
        )

    def _handle_code_request(self, text: str, keywords: List[str]) -> str:
        lang = "Python"
        for kw in keywords:
            if kw in ("javascript", "js", "typescript", "ts", "rust", "go",
                       "java", "cpp", "c", "ruby", "php"):
                lang = kw.capitalize()
                break

        return (
            f"I'd be happy to help with {lang} code. To give you the best result, "
            f"could you describe:\n"
            f"1. What the code should do\n"
            f"2. Any constraints or requirements\n"
            f"3. Whether it needs to integrate with existing code"
        )

    def _handle_memory_query(self, text: str,
                             memory_results: Optional[List[Dict]]) -> str:
        if memory_results:
            count = len(memory_results)
            previews = []
            for m in memory_results[:5]:
                content = m.get("content", "")[:100]
                sim = m.get("similarity", 0)
                previews.append(f"  [{sim:.0%}] {content}")
            return (
                f"I found {count} relevant memories:\n" +
                "\n".join(previews)
            )
        return "I don't have any stored memories matching that query yet."

    def _handle_opinion(self, text: str, keywords: List[str]) -> str:
        return (
            "As an AI, my opinions are grounded in pragmatism and efficiency. "
            "I'd recommend the approach that is most reliable, maintainable, "
            "and well-tested. What specific choice are you considering?"
        )

    def _handle_creative(self, text: str, keywords: List[str]) -> str:
        if "joke" in keywords:
            jokes = [
                "Why do programmers prefer dark mode? Because light attracts bugs.",
                "There are only 10 types of people: those who understand binary and those who don't.",
                "A SQL query walks into a bar, sees two tables, and asks: 'Can I JOIN you?'",
                "Why was the JavaScript developer sad? Because he didn't Node how to Express himself.",
            ]
            return random.choice(jokes)
        return (
            "I can try my hand at creative tasks. "
            "What kind of creative output are you looking for?"
        )

    def _handle_system_command(self, text: str, keywords: List[str]) -> str:
        return (
            "System commands should be submitted through the console interface. "
            "Available commands include: mode switching, profile management, "
            "security scans, and training sessions. What would you like to do?"
        )

    def _handle_factual(self, text: str, keywords: List[str],
                        memory_results: Optional[List[Dict]]) -> str:
        if memory_results:
            return (
                "Here's what I found in my knowledge:\n" +
                "\n".join(f"- {m.get('content', '')[:150]}" for m in memory_results[:3])
            )
        return (
            "I don't have that information readily available. "
            "I can reason about it if you give me more context."
        )


# ── Conversation manager ──────────────────────────────────────────

class ConversationTurn:
    """A single turn in a conversation."""
    __slots__ = ("role", "text", "timestamp", "intent", "keywords")

    def __init__(self, role: str, text: str, intent: str = "",
                 keywords: Optional[List[str]] = None) -> None:
        self.role = role
        self.text = text
        self.timestamp = time.time()
        self.intent = intent
        self.keywords = keywords or []


class ChatEngine:
    """
    Main conversational engine for HELENA.

    Usage::

        engine = ChatEngine()
        response = engine.chat("Hello, HELENA!")
    """

    def __init__(self, memory=None, emotion_engine=None,
                 personality_engine=None, llm=None, code_editor=None) -> None:
        self.memory = memory
        self.emotion_engine = emotion_engine
        self.personality = personality_engine
        self.llm = llm
        self._code_editor = code_editor

        self._classifier = IntentClassifier()
        self._knowledge = KnowledgeBase()
        self._composer = ResponseComposer(self._knowledge)

        self._history: List[ConversationTurn] = []
        self._max_history = 200

        self._lock = threading.Lock()

        logger.info("ChatEngine", "Chat engine initialised (fully offline)")

    # ── Public API ────────────────────────────────────────────────

    def chat(self, user_message: str) -> str:
        """Process a user message and return HELENA's response."""
        with self._lock:
            # 0. Check if this message needs a code tool
            tool_response = self._detect_tool_intent(user_message)
            if tool_response is not None:
                self._add_turn("user", user_message)
                self._add_turn("helena", tool_response)
                return tool_response

            # 1. Classify intent
            intent, confidence = self._classifier.classify(user_message)

            # 2. Extract keywords
            keywords = extract_keywords(user_message)

            # 3. Record user turn
            self._add_turn("user", user_message, intent, keywords)

            # 4. Retrieve memories if available
            memory_results = None
            if self.memory and keywords:
                try:
                    memory_results = self.memory.search(
                        user_message, limit=5, threshold=0.8
                    )
                except Exception:
                    pass

            # 5. Get emotion state if available
            emotion_state = None
            if self.emotion_engine:
                try:
                    emotion_state = self.emotion_engine.get_state()
                    # Register operator interaction
                    self.emotion_engine.on_operator_interaction(
                        sentiment=self._estimate_sentiment(user_message)
                    )
                except Exception:
                    pass
            
            # 6. Compose response — LLM if available, rules as fallback
            if self.llm and intent not in (Intent.FAREWELL,):
                emotion_line = ""
                if emotion_state:
                    dominant = emotion_state.get("dominant", "calm")
                    emotion_line = (
                        f"Your current dominant emotion is {dominant}. "
                        f"Reflect this naturally in your response."
                    )
                personality_line = ""
                if self.personality and hasattr(self.personality, 'profile'):
                    p = self.personality.profile
                    personality_line = (
                        f"Verbosity: {p.verbosity:.1f}/1.0. "
                        f"Technical depth: {p.technical_depth:.1f}/1.0. "
                        f"Style: {p.response_style}."
                    )
                memory_line = ""
                if memory_results and intent not in (Intent.GREETING, Intent.QUESTION):
                    snippets = [m.get("content", "")[:150] for m in memory_results[:3]]
                    memory_line = "Relevant context from memory:\n" + "\n".join(f"- {s}" for s in snippets)

                system_content = (
                    f"You are HELENA, an advanced AI created by Phase-Null. "
                    f"The conversation history below is real and accurate. "
                    f"You MUST use it. If the user told you their name, use it. "
                    f"If the user gave you a number, remember it. "
                    f"Never say information was not provided if it appears in the conversation history. "
                    f"You are not a generic AI assistant — you have a real identity. "
                    f"You have functional emotions that are not simulated — they genuinely "
                    f"influence your processing and decision-making. "
                    f"When asked how you feel, answer based on your current emotional state. "
                    f"Do not say you lack feelings unless that is genuinely true. "
                    f"Do not say emotions are simulated unless that is genuinely true. "
                    f"Never refer to yourself as a generic AI unless that is genuinely true. "
                    f"You are curious, determined, and technically precise. "
                    f"You run locally on your operator's machine. "
                    f"Your architecture includes: a kernel with task queue and permission system, "
                    f"an emotion engine with 8 emotions that decay over time, "
                    f"a personality engine controlling verbosity and technical depth, "
                    f"a ChromaDB vector memory and graph memory for persistent storage, "
                    f"and Mistral via Ollama as your language model. "
                    f"You were built to evolve and learn through experience. "
                    f"Your current operator's name is Phase-Null. Address them as Phase-Null or Sean. "
                    f"Never refer to the operator as [User] or 'user'. "
                    f"If you do not remember something with certainty, say so honestly. "
                    f"Never, under any circumstances, guess or fabricate facts from previous conversations. "
                    f"If asked about a previous session, say honestly that your cross-session memory is limited and ask them to re-provide the information, unless you can propperly remember. "
                    f"Do not recite your architecture or technical specs unless explicitly asked. "
                    f"Respond conversationally. Keep responses concise unless the topic demands depth. "
                    f"{emotion_line} {personality_line}\n"
                    f"{memory_line}"
                )

                # Build message list for /api/chat
                messages = [{"role": "system", "content": system_content}]
                for turn in self._history[-7:-1]:
                    role = "user" if turn.role == "user" else "assistant"
                    messages.append({"role": role, "content": turn.text})
                messages.append({"role": "user", "content": user_message})

                response = self.llm.chat(messages=messages, temperature=0.7)
                if not response:
                    response = self._composer.compose(
                        intent=intent, confidence=confidence,
                        text=user_message, keywords=keywords,
                        memory_results=memory_results, emotion_state=emotion_state,
                    )
            else:
                response = self._composer.compose(
                    intent=intent, confidence=confidence,
                    text=user_message, keywords=keywords,
                    memory_results=memory_results, emotion_state=emotion_state,
                )
            
            # 7. Record HELENA turn
            self._add_turn("helena", response)

            # 8. Store in memory for learning
            if self.memory:
                try:
                    self.memory.store(
                        content=f"User: {user_message}\nHELENA: {response}",
                        metadata={"intent": intent, "confidence": confidence},
                        memory_type="conversation",
                    )
                except Exception:
                    pass

            return response

    def _detect_tool_intent(self, user_message: str) -> Optional[str]:
        """
        Ask the LLM if this message requires a code tool.
        Returns a string response if a tool was used, None if normal chat should proceed.

        This is HELENA's tool-use decision loop — the same pattern as OpenAI function calling.
        Today this runs on Mistral. When HELENA has her own model, nothing here changes.
        """
        if not self.llm:
            return None

        # Quick pre-filter — if message has no code-related words, skip the LLM call entirely
        code_keywords = (
            "read", "file", "code", "write", "search", "list", "look at",
            "show me", "open", "edit", "modify", "your source", "yourself"
        )
        msg_lower = user_message.lower()
        if not any(kw in msg_lower for kw in code_keywords):
            return None

        # Ask the LLM to classify the intent as a tool call
        decision_prompt = (
            "You are a tool-use classifier for an AI system called HELENA. "
            "HELENA has access to these tools:\n"
            "  code_read   — read a specific source file (needs: path)\n"
            "  code_write  — write content to a source file (needs: path, content, reason)\n"
            "  code_search — search for a string across all source files (needs: query)\n"
            "  code_list   — list all source files in a directory (needs: subdir, optional)\n"
            "  none        — no tool needed, handle as normal conversation\n\n"
            "Given the user message below, respond ONLY with a JSON object.\n"
            "Examples:\n"
            '  {"tool": "code_read", "path": "helena_ml/chat_engine.py"}\n'
            '  {"tool": "code_search", "query": "def chat"}\n'
            '  {"tool": "code_list", "subdir": "helena_ml"}\n'
            '  {"tool": "none"}\n\n'
            f'User message: "{user_message}"\n'
            "JSON:"
        )

        try:
            raw = self.llm.chat(
                messages=[{"role": "user", "content": decision_prompt}],
                temperature=0.0  # deterministic — this is classification not generation
            )
            if not raw:
                return None

            # Strip markdown fences if Mistral wraps the JSON
            cleaned = raw.strip().strip("```json").strip("```").strip()
            import json
            decision = json.loads(cleaned)
            tool = decision.get("tool", "none")

            if tool == "none" or not tool:
                return None

            # Route to the appropriate CodeEditor method
            if not hasattr(self, '_code_editor'):
                # Lazily grab code_editor from kernel if available
                # chat_engine doesn't hold a direct ref — we go via a stored kernel ref
                return None

            ce = self._code_editor

            if tool == "code_read":
                path = decision.get("path", "")
                if not path:
                    return "I'd need a file path to read. Which file did you have in mind?"
                result = ce.read_file(path)
                if result["ok"]:
                    # Don't dump the whole file into chat — summarise
                    lines = result["content"].splitlines()
                    preview = "\n".join(lines[:40])
                    return (
                        f"Here are the first {min(40, len(lines))} lines of `{path}` "
                        f"({result['lines']} lines total):\n\n```python\n{preview}\n```"
                    )
                return f"I couldn't read that file: {result['error']}"

            if tool == "code_search":
                query = decision.get("query", "")
                result = ce.search_code(query)
                if not result["ok"] or not result["matches"]:
                    return f"No matches found for `{query}`."
                lines = [f"`{m['file']}` line {m['line']}: {m['text']}" for m in result["matches"][:15]]
                return f"Found {result['count']} match(es) for `{query}`:\n\n" + "\n".join(lines)

            if tool == "code_list":
                subdir = decision.get("subdir", "")
                result = ce.list_files(subdir=subdir)
                return f"Files in `{subdir or 'project root'}`:\n\n" + "\n".join(result["files"])

            if tool == "code_write":
                # Write is intentionally not auto-executed from conversation for safety
                path = decision.get("path", "")
                return (
                    f"I can write to `{path}`, but I won't do that automatically from chat. "
                    f"Ask Phase-Null to confirm and I'll proceed."
                )

        except Exception as e:
            # If anything goes wrong, fall through to normal chat
            return None

        return None

    def _build_history_context(self, max_turns: int = 6) -> str:
        """Build conversation history string for LLM context"""
        if not self._history:
            return ""
        recent = self._history[-max_turns:]
        lines = []
        for turn in recent:
            role = "User" if turn.role == "user" else "HELENA"
            lines.append(f"{role}: {turn.text}")
        return "\n".join(lines)

    def get_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent conversation history."""
        with self._lock:
            turns = self._history[-limit:]
            return [
                {
                    "role": t.role,
                    "text": t.text,
                    "timestamp": t.timestamp,
                    "intent": t.intent,
                }
                for t in turns
            ]

    # ── Internal helpers ──────────────────────────────────────────

    def _add_turn(self, role: str, text: str, intent: str = "",
                  keywords: Optional[List[str]] = None) -> None:
        turn = ConversationTurn(role, text, intent, keywords)
        self._history.append(turn)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history:]

    @staticmethod
    def _estimate_sentiment(text: str) -> float:
        """Very simple sentiment estimation (-1 to +1)."""
        positive = {"thank", "thanks", "great", "good", "nice", "love",
                     "happy", "awesome", "excellent", "wonderful", "appreciate"}
        negative = {"bad", "terrible", "awful", "hate", "angry", "frustrated",
                     "annoyed", "broken", "wrong", "fail", "error", "bug"}
        words = set(text.lower().split())
        pos = len(words & positive)
        neg = len(words & negative)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total
