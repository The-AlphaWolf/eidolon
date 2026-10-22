"""Entity ID aliases (§4.4: "every actor/location/object slot is an ID, never a string").

Plain `str` aliases: name-to-ID resolution against the case `Alias` table (§4.11) is a
parser-time concern (Phase 5); the world model only needs the ID to be stable and hashable.
"""
ActorId = str
LocationId = str
ObjectId = str
EventId = str
EvidenceId = str
DoorId = str
