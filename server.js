const express = require("express");
const cors = require("cors");
const { default: axios } = require("axios");
const app = express();
const PORT = process.env.PORT || 8000;

const { v4: uuidv4 } = require("uuid");

const dummyData = require("./dummy_data.json");

app.use(cors());
app.use(express.json());
app.use(express.static("public"));

// PROD | STG | DEV
const FROM = "PROD"

async function useGenerateFrom(req) {
  if (FROM === "PROD") {
    const targetUrl = "https://photon-api.thesynapses.com/generate";

    return axios({
      method: "post",
      url: targetUrl,
      data: {
        ...req.body,
        type: "global",
        file_url: [],
        org_id: "synapse",
        uid: "oB3qkWuOcTVh21NGWHudqFrxxmt1",
        regenerate: false,
        style: "Standard",
        recaching: false,
        cache_id: null,
        file_data: "",
        prompt_id: "41818501-5e4b-4dfe-8474-95e723437c22",
        new_prompt: "",
        by: "oB3qkWuOcTVh21NGWHudqFrxxmt1",
      },
      headers: {
        "Content-Type": "application/json",
      },
      responseType: "stream",
    });  
  } else if (FROM === "STG") {
    const targetUrl = "https://photon-api.thesynapses.com/generate";

    return axios({
      method: "post",
      url: targetUrl,
      data: {
        ...req.body,
        type: "global",
        file_url: [],
        org_id: "synapses",
        uid: "xePSzT4DmZQ8G9UkUyeGtF5GEyP2",
        regenerate: false,
        style: "Standard",
        recaching: false,
        cache_id: null,
        file_data: "",
        prompt_id: "e5bd012b-b55a-4364-ae8b-50188234214a",
        new_prompt: "",
        by: "xePSzT4DmZQ8G9UkUyeGtF5GEyP2",
        session_id: "xePSzT4DmZQ8G9UkUyeGtF5GEyP2",
      },
      headers: {
        "Content-Type": "application/json",
      },
      responseType: "stream",
    });  
  }
  return null
} 

function useModelsFrom() {
  if (FROM === "PROD") return ({
    models: [
      {
        id: "claude-opus-4@20250514",
        name: "Noney 1.0 Twinkle",
        google_search: false,
        active: "True",
        from: "NONEY",
        description: "High-end and smart.",
      },
      {
        id: "gemini-2.5-pro-preview-05-06",
        name: "Noney 1.0 Pro",
        google_search: true,
        active: "True",
        from: "NONEY",
        description: "Advanced and powerful.",
      },
      {
        id: "gemini-2.5-flash-preview-05-20",
        name: "Gemini 2.5 Flash",
        google_search: true,
        active: "True",
        from: "GEMINI",
        description: "Fast, smart, and web-ready.",
      },
      {
        id: "claude-sonnet-4@20250514",
        name: "Claude Sonnet 4",
        google_search: false,
        active: "True",
        from: "CLAUDE",
        description: "Smooth and balanced.",
      },
    ],
    default_model: {
      id: "claude-opus-4@20250514",
      name: "Noney 1.0 Twinkle",
      google_search: false,
      active: "True",
      from: "NONEY",
      description: "High-end and smart.",
    },
  })
  
  return {}
}

app.get("/get_models", (req, res) => {
  res.json(useModelsFrom());
});

app.post("/summarise_title", async (req, res) => {
  const { prompt } = req.body;
  if (!prompt) {
    return res.status(400).json({ error: "Prompt is required" });
  }
  const response = await axios.post(
    "https://pa-dev-api.thesynapses.com/summarise_title",
    {
      prompt: prompt,
      prompt_id: "99bc553f-529c-45ed-8a75-f98cce1aa2a5",
      org_id: "synapses",
      chat_id: "48472b3b-9883-4ba3-a855-1d97adaffd33",
      user_id: "un2xqHu71cd6WWycTr1P6UE4PiJ2",
    }
  );

  res.json(response.data);
});

app.post("/generate", async (req, res) => {
  try {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    res.write(
      `event: step\ndata: ${JSON.stringify({
        id: uuidv4(),
        data: [
          {
            type: "connecting",
            title: "Please Wait",
            description:
              "Search for the latest news on the Iran-Israel conflict",
          },
        ],
      })}\n\n`
    );
    

    res.write(
      `event: step\ndata: ${JSON.stringify({
        id: uuidv4(),
        data: [
          {
            type: "searching",
            title: "Searching",
          },
        ],
      })}\n\n`
    );

    const id = uuidv4();
    
    const response = await useGenerateFrom(req);
    response.data.on("data", (chunk) => {
      const content = chunk.toString();
      if (content) {
        const data = {
          index: 0,
          id: id,
          data: content,
        };
        res.write(`event: text\ndata: ${JSON.stringify(data)}\n\n`);
      }
    });

    response.data.on("end", () => {
      res.write(
        `event: step\ndata: ${JSON.stringify({
          id: uuidv4(),
          data: [
            {
              type: "finished",
              title: "Finished",
            },
          ],
        })}\n\n`
      );
      res.write("event: end\ndata: [DONE]\n\n");
      res.end();
    });

    response.data.on("error", (err) => {
      console.log("error", err.message)
      res.write(
        `event: error\ndata: ${JSON.stringify({ error: err.message })}\n\n`
      );
      res.end();
    });
  } catch (error) {
    console.error("Proxy error:", error.message);
    res.status(500).json({ error: "Failed to proxy /generate" });
  }
});

app.post("/generate_v2", async (req, res) => {
  try {
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");

    const randomIndex = Math.floor(Math.random() * dummyData.length);
    const data_to_stream = dummyData[randomIndex];

    let index = 0;
    for (let i = 0; i < data_to_stream.length; i++) {
      const item = data_to_stream[i];
      const id = uuidv4();

      if (item.type === "text") {
        const fullText = item.data;
        let pointer = 0;

        while (pointer < fullText.length) {
          const chunkSize = Math.floor(Math.random() * (50 - 20 + 1)) + 20; // random size between 5 and 20
          const textChunk = fullText.slice(pointer, pointer + chunkSize);
          pointer += chunkSize;
          const chunkData = {
            index: index,
            id: id,
            data: textChunk,
          };

          res.write(`event: text\ndata: ${JSON.stringify(chunkData)}\n\n`);

          const delay = Math.floor(Math.random() * (300 - 100 + 1)) + 100;
          await new Promise((resolve) => setTimeout(resolve, delay));
        }
      } else if (item.type === "step" || item.type === "source") {
        const data = {
          id: id,
          data: item.data,
        };

        res.write(`event: ${item.type}\ndata: ${JSON.stringify(data)}\n\n`);

        const delay = Math.floor(Math.random() * (300 - 100 + 1)) + 100;
        await new Promise((resolve) => setTimeout(resolve, delay));
      } else {
        const data = {
          index: index,
          id: id,
          data: item.data,
        };

        res.write(`event: ${item.type}\ndata: ${JSON.stringify(data)}\n\n`);

        const delay = Math.floor(Math.random() * (300 - 100 + 1)) + 100;
        await new Promise((resolve) => setTimeout(resolve, delay));
      }

      if (item.type !== "step" && item.type !== "source") {
        index++;
      }
    }

    res.end();
  } catch (error) {
    console.error("Error:", error.message);
    res.status(500).json({ error: "Failed" });
  }
});

app.get("/health", (req, res) => {
  res.json({ status: "ok" });
});

app.listen(PORT, () => {
  console.log(`Server running on http://localhost:${PORT}`);
});
