"use client";

interface SessionTimeoutModalProps {
  open: boolean;
  countdownSeconds: number;
  onDismiss: () => void;
  onLogout: () => void;
}

export function SessionTimeoutModal({ open, countdownSeconds, onDismiss, onLogout }: SessionTimeoutModalProps) {
  if (!open) return null;

  const minutes = Math.floor(countdownSeconds / 60);
  const seconds = countdownSeconds % 60;
  const timeDisplay = `${minutes}:${seconds.toString().padStart(2, "0")}`;
  const isUrgent = countdownSeconds <= 30;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-[#1a1a2e] border border-gray-800 rounded-lg p-6 shadow-xl w-full max-w-sm mx-4">
        <div className="flex items-center gap-3 mb-4">
          <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold ${isUrgent ? "bg-red-600 text-white animate-pulse" : "bg-amber-600 text-white"}`}>
            {isUrgent ? "!" : "\u23F3"}
          </div>
          <div>
            <h3 className="text-lg font-semibold text-gray-800 dark:text-gray-100">Session Expiring</h3>
            <p className="text-sm text-gray-600 dark:text-gray-400">You will be logged out automatically</p>
          </div>
        </div>

        <div className="text-center mb-5">
          <span className={`text-4xl font-mono font-bold ${isUrgent ? "text-red-500" : "text-amber-500"}`}>
            {timeDisplay}
          </span>
        </div>

        <p className="text-sm text-gray-600 dark:text-gray-400 text-center mb-5">
          Your session will expire in 30 seconds due to inactivity.
        </p>

        <div className="flex flex-col gap-2">
          <button
            onClick={onDismiss}
            className="w-full px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-md font-medium transition-colors"
          >
            Stay logged in
          </button>
          <button
            onClick={onLogout}
            className="w-full px-4 py-2 border border-red-600/60 text-red-400 hover:bg-red-600/10 rounded-md font-medium transition-colors"
          >
            Log out now
          </button>
        </div>
      </div>
    </div>
  );
}
