import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.Socket;
import java.nio.charset.StandardCharsets;

/**
 * LineConn
 * --------
 * Turns a raw TCP socket into "read one line, send one line". TCP is a byte
 * stream, not a message stream, so a single read() can return half a
 * command, one whole command, or several -- this class buffers bytes
 * per-connection and only hands back a line once a full '\n' has arrived.
 *
 * Used identically by every TCP link in the system: client<->KvServer,
 * client<->Proxy, and Proxy<->backend.
 */
public class LineConn {
    public final Socket socket;
    private final InputStream in;
    private final OutputStream out;
    private byte[] buf = new byte[0];

    public LineConn(Socket socket) throws IOException {
        this.socket = socket;
        this.in = socket.getInputStream();
        this.out = socket.getOutputStream();
    }

    /** Reads one '\n'-terminated line, blocking until a full line has
     * arrived. Throws ConnectionClosedException if the peer hung up
     * (a read() of -1, TCP's EOF signal) before a full line showed up. */
    public String readLine() throws IOException, ConnectionClosedException {
        int nl;
        while ((nl = indexOfNewline(buf)) == -1) {
            byte[] chunk = new byte[4096];
            int n = in.read(chunk);
            if (n == -1) {
                throw new ConnectionClosedException();
            }
            byte[] merged = new byte[buf.length + n];
            System.arraycopy(buf, 0, merged, 0, buf.length);
            System.arraycopy(chunk, 0, merged, buf.length, n);
            buf = merged;
        }
        String line = new String(buf, 0, nl, StandardCharsets.UTF_8);
        byte[] rest = new byte[buf.length - nl - 1];
        System.arraycopy(buf, nl + 1, rest, 0, rest.length);
        buf = rest;
        return line;
    }

    public void sendLine(String line) throws IOException {
        out.write((line + "\n").getBytes(StandardCharsets.UTF_8));
        out.flush();
    }

    public void close() {
        try {
            socket.close();
        } catch (IOException ignored) {
        }
    }

    private static int indexOfNewline(byte[] b) {
        for (int i = 0; i < b.length; i++) {
            if (b[i] == '\n') return i;
        }
        return -1;
    }
}
