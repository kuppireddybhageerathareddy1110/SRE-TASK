import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.util.concurrent.locks.ReentrantLock;

/**
 * One persistent link to one KvServer, plus what the proxy currently
 * believes about it. `up` and `readReady` are deliberately separate --
 * a backend spends real time with up=true, readReady=false (mid catch-up).
 */
public class Backend {
    public final String host;
    public final int port;
    public final String name;

    private final ReentrantLock lock = new ReentrantLock();
    private LineConn conn;

    public volatile boolean up = false;
    public volatile boolean readReady = false;
    public volatile boolean catchingUp = false;
    public volatile boolean everChecked = false;

    public Backend(String host, int port, String name) {
        this.host = host;
        this.port = port;
        this.name = name;
    }

    public String address() {
        return host + ":" + port;
    }

    /** One request/response round trip. Returns null (and drops the
     * connection so the next call reconnects) on any failure -- caller
     * decides what that means for up/readReady. */
    public String call(String line, double timeoutSeconds) {
        lock.lock();
        try {
            int timeoutMs = (int) Math.max(1, timeoutSeconds * 1000);
            if (conn == null) {
                Socket sock = new Socket();
                sock.connect(new InetSocketAddress(host, port), timeoutMs);
                sock.setSoTimeout(timeoutMs);
                conn = new LineConn(sock);
            }
            conn.socket.setSoTimeout(timeoutMs);
            conn.sendLine(line);
            return conn.readLine();
        } catch (IOException | ConnectionClosedException e) {
            if (conn != null) conn.close();
            conn = null;
            return null;
        } finally {
            lock.unlock();
        }
    }
}
