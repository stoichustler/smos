# IPC

## Channel

A channel is a bidirectional transport of messages consisting of some
amount of byte data and some number of handles.

Channels have two endpoints. Each endpoint, logically, maintains an ordered
queue of messages to be read. Writing to an endpoint enqueues a message in the
other endpoint's queue. When the last handle to an endpoint is closed the unread
messages in that endpoint's queue are destroyed. Because destroying a message
closes any handles contained by the message, closing a channel endpoint may have
a recursive effect (e.g. channel contains a message, which contains a channel,
which contains a message, and so on).

Closing the last handle to a channel has no impact on the lifetime of messages
previously written to that channel. This gives channels "fire and forget"
semantics.

A message consists of some amount of data and some number of handles. A call to
[`zx_channel_write()`] enqueues one message, and a call to [`zx_channel_read()`]
dequeues one message (if any are queued). A thread can block until messages are
pending via [`zx_object_wait_one()`] or other waiting mechanisms.

Alternatively, a call to [`zx_channel_call()`] enqueues a message in one
direction of the channel, waits for a corresponding response, and
dequeues the response message. In call mode, corresponding responses
are identified via the first 4 bytes of the message, called the
transaction ID. The kernel supplies distinct transaction IDs (always with the
high bit set) for messages written with [`zx_channel_call()`].

The process of sending a message via a channel has two steps. The first is to
atomically write the data into the channel and move ownership of all handles in
the message into this channel. This operation always consumes the handles: at
the end of the call, all handles either are all in the channel or are all
discarded. The second operation, channel read, is similar: on success
all the handles in the next message are atomically moved into the
receiving process' handle table. On failure, the channel retains
ownership unless the **ZX_CHANNEL_READ_MAY_DISCARD** option
is specified, then they are dropped.

Unlike many other kernel object types, channels are not duplicatable. Thus, there
is only ever one handle associated with a channel endpoint, and the process holding
that handle is considered the owner. Only the owner can read or write messages or send
the channel endpoint to another process.

When ownership of a channel endpoint moves from one process to another,
messages will not be reordered or truncated, even if a write is in progress.
Messages before the transfer event belong to the previous owner and messages
after the transfer belong to the new owner.
The same applies if a read is in progress when the endpoint is transferred.

The above sequential guarantee is not provided for other kernel objects, even if
the last remaining handle is stripped of the **ZX_RIGHT_DUPLICATE** right.

## Socket

Sockets are a bidirectional stream transport. Unlike channels, sockets
only move data (not handles).

Data is written into one end of a socket via [`zx_socket_write()`] and
read from the opposing end via [`zx_socket_read()`].

Upon creation, both ends of the socket are writable. Using the
[`zx_socket_set_disposition()`] system call, each end of the socket can be
enabled or disabled independently, using the
**ZX_SOCKET_DISPOSITION_WRITE_ENABLED** and
**ZX_SOCKET_DISPOSITION_WRITE_DISABLED**.

The following properties may be queried from a socket object:

**ZX_PROP_SOCKET_RX_THRESHOLD** size of the read threshold of a socket, in
bytes. When the bytes queued on the socket (available for reading) is equal to
or greater than this value, the **ZX_SOCKET_READ_THRESHOLD** signal is asserted.
Read threshold signalling is disabled by default (and when set, writing
a value of 0 for this property disables it).

**ZX_PROP_SOCKET_TX_THRESHOLD** size of the write threshold of a socket,
in bytes. When the space available for writing on the socket is equal to or
greater than this value, the **ZX_SOCKET_WRITE_THRESHOLD** signal is asserted.
Write threshold signalling is disabled by default (and when set, writing a
value of 0 for this property disables it).

From the point of view of a socket handle, the receive buffer contains the data
that is readable via [`zx_socket_read()`] from that handle (having been written
from the opposing handle), and the transmit buffer contains the data that is
written via [`zx_socket_write()`] to that handle (and readable from the opposing
handle).

The following signals may be set for a socket object:

**ZX_SOCKET_READABLE** data is available to read from the socket

**ZX_SOCKET_WRITABLE** data may be written to the socket

**ZX_SOCKET_PEER_CLOSED** the other endpoint of this socket has
been closed.

**ZX_SOCKET_PEER_WRITE_DISABLED** writing is disabled for the other
endpoint because its disposition was set to
**ZX_SOCKET_DISPOSITION_WRITE_DISABLED**. Reads on a socket endpoint with this
signal raised will succeed so long as there is data in the socket that was
written before writing was disabled.

**ZX_SOCKET_WRITE_DISABLED** writing is disabled for this endpoint because its
disposition was set to **ZX_SOCKET_DISPOSITION_WRITE_DISABLED**. Writes on a
socket endpoint with this signal raised will fail.

**ZX_SOCKET_READ_THRESHOLD** data queued up on socket for reading exceeds
the read threshold.

**ZX_SOCKET_WRITE_THRESHOLD** space available on the socket for writing exceeds
the write threshold.

## FIFO

FIFOs are intended to be the control plane for shared memory
transports.  Their read and write operations are more efficient than
[sockets](socket.md) or [channels](channel.md), but there are severe
restrictions on the size of elements and buffers.

## Peered object and the peer-closed state

Currently, the kernel defines the following object types as "peered" objects.

All peered objects are created in pairs, which are internally linked to each
other in a peer relationship.  When the active handle count of a peered object
reaches 0, if that object still has a link to its peer, the peer object will be
placed in the `PEER_CLOSED` state, causing the link to be destroyed, the
specific `ZX_*_PEER_CLOSED` signal to become asserted on the peer, and for
syscalls involving the object's peer (for example, `zx_channel_write`) to return
the error `ZX_ERR_PEER_CLOSED`.

When the final handle to an object is closed via a call to [`zx_handle_close`],
or [`zx_handle_close_many`], it is guaranteed that the object's peer (if any)
will be placed into the `PEER_CLOSED` state, asserting its associated signal in
the process, before the `zx_handle_close` syscall returns from the kernel.

Note that objects are placed into `PEER_CLOSED` when their peer's _active handle
count_ has hit zero, even of the peer object continues to live because of a
direct pointer reference held by the kernel.

---

SMOS [Microkernel]
