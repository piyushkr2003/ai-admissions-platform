"use client";

/**
 * Thin wrapper around the `livekit-client` browser SDK (Task 015). Kept
 * as its own module so components depend on a small, mockable surface
 * instead of importing `livekit-client` directly - `vi.mock("@/lib/voice/livekit-room")`
 * is what makes the voice console testable under jsdom, which has no
 * WebRTC stack at all.
 */
import { Room, RoomEvent, type DisconnectReason } from "livekit-client";

export type VoiceRoomHandlers = {
  onDisconnected?: (reason: DisconnectReason | undefined) => void;
  onReconnecting?: () => void;
  onReconnected?: () => void;
};

export type VoiceRoomHandle = {
  room: Room;
  disconnect: () => Promise<void>;
};

/**
 * Connects to a LiveKit room and publishes the local microphone track.
 * Throws whatever `getUserMedia`/room.connect throws (e.g. a
 * `NotAllowedError` DOMException on microphone denial, or a network
 * error on an unreachable server) - the caller is responsible for
 * turning that into a user-facing message; this module never swallows
 * or fakes a successful connection.
 */
export async function connectVoiceRoom(
  serverUrl: string,
  token: string,
  handlers: VoiceRoomHandlers = {},
): Promise<VoiceRoomHandle> {
  const room = new Room();

  room.on(RoomEvent.Disconnected, (reason) => handlers.onDisconnected?.(reason));
  room.on(RoomEvent.Reconnecting, () => handlers.onReconnecting?.());
  room.on(RoomEvent.Reconnected, () => handlers.onReconnected?.());

  await room.connect(serverUrl, token);
  await room.localParticipant.setMicrophoneEnabled(true);

  return {
    room,
    disconnect: async () => {
      await room.disconnect();
    },
  };
}
