package main

import (
	"bufio"
	"encoding/csv"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"maps"
	"net/http"
	"os"
	"slices"
	"strconv"
	"strings"

	"github.com/line/line-bot-sdk-go/v8/linebot/messaging_api"
	"github.com/line/line-bot-sdk-go/v8/linebot/webhook"
	"github.com/sahilm/fuzzy"
)

var gameIds []string
var lineIds []string
var rules string
var commonNames map[string]string
var wikiPages []string
var itemDataMap map[string][]map[string]any
var allItems []string

func correctItemName(text string) string {
	if value, ok := commonNames[text]; ok {
		return value
	}
	return text
}

func getRules() *messaging_api.TextMessage {
	return &messaging_api.TextMessage{Text: rules}
}

func findWiki(item string) *messaging_api.TextMessage {
	item = correctItemName(item)
	urlFmt := "https://hackersthegame.fandom.com/wiki/%s"
	matched := []string{}
	var result string
	for _, match := range fuzzy.Find(item, wikiPages) {
		matched = append(matched, match.Str)
	}

	if len(matched) == 1 {
		result = fmt.Sprintf(urlFmt, matched[0])
	} else if len(matched) > 1 {
		if slices.Contains(matched, item) {
			result = fmt.Sprintf(urlFmt, item)
		} else {
			matched = append([]string{"您是不是要查:"}, matched...)
			result = strings.Join(matched, "\n")
		}
	} else {
		return nil
	}

	return &messaging_api.TextMessage{Text: result}
}

func findData(item string, level int) *messaging_api.TextMessage {
	if level <= 0 {
		return nil
	}
	item = correctItemName(item)

	itemData, ok := itemDataMap[item]

	if !ok {
		matched := []string{}
		for _, match := range fuzzy.Find(item, allItems) {
			matched = append(matched, match.Str)
		}

		if len(matched) == 1 {
			itemData = itemDataMap[matched[0]]
		} else if len(matched) > 1 {
			matched = append([]string{"您是不是要查:"}, matched...)
			return &messaging_api.TextMessage{Text: strings.Join(matched, "\n")}
		} else {
			return nil
		}
	}

	if len(itemData) <= level {
		const replyfmt string = "%s 沒有等級 %d"
		return &messaging_api.TextMessage{Text: fmt.Sprintf(replyfmt, item, level)}
	}

	levelData := itemData[level]
	return &messaging_api.TextMessage{Text: levelData["data_string"].(string)}
}

func findUser(name string) *messaging_api.TextMessage {
	if gameIds == nil || lineIds == nil {
		return nil
	}

	uniqueResult := map[string]struct{}{}
	for _, match := range fuzzy.Find(name, gameIds) {
		uniqueResult[fmt.Sprintf("%s --> %s", lineIds[match.Index], match.Str)] = struct{}{}
	}

	for _, match := range fuzzy.Find(name, lineIds) {
		uniqueResult[fmt.Sprintf("%s --> %s", match.Str, gameIds[match.Index])] = struct{}{}
	}

	temp := slices.Collect(maps.Keys(uniqueResult))
	if len(temp) == 0 || len(temp) > 10 {
		return nil
	}

	result := strings.Join(temp, "\n")
	return &messaging_api.TextMessage{Text: result}
}

func webhookHandler(text string, resp *[]messaging_api.MessageInterface) {
	commands := strings.Split(text, " ")
	nCommand := len(commands)
	if nCommand < 2 || commands[0] != "貓" {
		return
	}

	if nCommand == 2 {
		if commands[1] == "群規" {
			*resp = append(*resp, getRules())
			return
		}
		if result := findUser(commands[1]); result != nil {
			*resp = append(*resp, result)
		}
		if result := findWiki(correctItemName(commands[1])); result != nil {
			*resp = append(*resp, result)
		}
		return
	}

	if nCommand == 3 {
		item := correctItemName(commands[1])
		level, err := strconv.Atoi(commands[2])
		if err != nil {
			log.Print(err)
			return
		}

		if result := findData(item, level); result != nil {
			*resp = append(*resp, result)
		}
	}
}

func LoadNameData() {
	file, err := os.OpenFile("/etc/data/names.csv", os.O_RDONLY, 0644)
	if err != nil {
		log.Fatalln("File not found")
	}
	defer file.Close()
	r := csv.NewReader(file)
	for range 3 {
		r.Read()
	}
	for {
		record, err := r.Read()
		if err != nil {
			if err != io.EOF {
				log.Fatal(err)
			}
			break
		}
		gameIds = append(gameIds, record[2])
		lineIds = append(lineIds, record[4])
	}
}

func LoadItemData() {
	itemDataMap = make(map[string][]map[string]any)
	jsonData, err := os.ReadFile("/etc/data/data.json")
	if err != nil {
		log.Fatalln("File not found")
	}
	err = json.Unmarshal(jsonData, &itemDataMap)
	if err != nil {
		log.Fatalln("File not found")
	}
	allItems = slices.Collect(maps.Keys(itemDataMap))
}

func LoadCommonName() {
	commonNames = make(map[string]string)
	file, err := os.OpenFile("/etc/data/common_name.csv", os.O_RDONLY, 0644)
	if err != nil {
		log.Fatalln("File not found")
	}
	defer file.Close()
	r := csv.NewReader(file)
	for {
		record, err := r.Read()
		if err != nil {
			if err != io.EOF {
				log.Fatal(err)
			}
			break
		}
		commonNames[record[0]] = record[1]
	}
}

func LoadRuleData() {
	b, err := os.ReadFile("/etc/data/rules.txt")
	if err != nil {
		log.Fatal(err)
	}
	rules = strings.TrimSpace(string(b))
}

func LoadWikiPageData() {
	file, err := os.Open("/etc/data/wikipages.txt")
	if err != nil {
		log.Fatal(err)
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	for scanner.Scan() {
		line := scanner.Text()
		wikiPages = append(wikiPages, strings.TrimSpace(line))
	}

	if err := scanner.Err(); err != nil {
		log.Fatal(err)
	}
}

func Load() {
	LoadNameData()
	LoadRuleData()
	LoadCommonName()
	LoadWikiPageData()
	LoadItemData()
	fmt.Println("Load Success")
}

func main() {
	Load()
	handler, err := webhook.NewWebhookHandler(os.Getenv("LINE_CHANNEL_SECRET"))
	if err != nil {
		log.Fatal(err)
	}

	bot, err := messaging_api.NewMessagingApiAPI(os.Getenv("LINE_CHANNEL_TOKEN"))
	if err != nil {
		log.Fatal(err)
	}

	handler.HandleEvents(func(req *webhook.CallbackRequest, r *http.Request) {
		for _, event := range req.Events {
			switch e := event.(type) {
			case webhook.MessageEvent:
				switch message := e.Message.(type) {
				case webhook.TextMessageContent:
					resp_message := []messaging_api.MessageInterface{}
					webhookHandler(message.Text, &resp_message)
					if len(resp_message) != 0 {
						_, err := bot.ReplyMessage(
							&messaging_api.ReplyMessageRequest{
								ReplyToken: e.ReplyToken,
								Messages:   resp_message,
							},
						)
						if err != nil {
							log.Print(err)
						}
					}
				}
			}
		}
	})
	http.Handle("/", handler)
	if err := http.ListenAndServe(":8080", nil); err != nil {
		log.Fatal(err)
	}
}
