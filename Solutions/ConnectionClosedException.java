/**
 * Raised when the peer closed the socket (a read() of -1 -- TCP's
 * zero-byte-read EOF signal) instead of sending a line. Kept distinct
 * from an empty string so callers can't mistake "peer hung up" for
 * "peer sent a blank line".
 */
public class ConnectionClosedException extends Exception {
    public ConnectionClosedException() {
        super("connection closed by peer");
    }
}
